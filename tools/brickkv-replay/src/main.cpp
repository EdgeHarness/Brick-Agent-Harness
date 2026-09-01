#include "brickkv/lineage.hpp"
#include "brickkv/runtime_config.hpp"

#include <geniex.h>

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
#else
#include <fcntl.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

namespace {

using brickkv::Identity;
using brickkv::LineageGate;
using brickkv::Message;
using brickkv::Request;

struct Options {
    std::filesystem::path model;
    std::filesystem::path tokenizer;
    std::filesystem::path output;
    std::string plugin;
    std::string device = "npu";
    std::string mode = "managed";
    std::string trace = "all";
    std::string hardware_label;
    std::string source_revision;
    int context = 8192;
    int max_tokens = 32;
    int append_turns = 12;
    int cancel_after_tokens = 1;
};

struct Record {
    std::string trace;
    std::string mode;
    std::string role;
    std::string cache_status;
    std::string cache_reason;
    std::string revision;
    std::string stop_reason;
    std::string output_digest;
    int step = 0;
    int result_code = 0;
    std::int64_t ttft_us = 0;
    std::int64_t prompt_us = 0;
    std::int64_t decode_us = 0;
    std::int64_t prompt_tokens = 0;
    std::int64_t generated_tokens = 0;
    std::int64_t wall_us = 0;
    std::uint64_t working_set_bytes = 0;
    bool callback_cancelled = false;
};

struct Generation {
    Record record;
    std::string text;
};

std::string json_escape(const std::string_view value) {
    std::ostringstream out;
    for (const unsigned char ch : value) {
        switch (ch) {
        case '"': out << "\\\""; break;
        case '\\': out << "\\\\"; break;
        case '\b': out << "\\b"; break;
        case '\f': out << "\\f"; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default:
            if (ch < 0x20U) {
                out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                    << static_cast<unsigned int>(ch) << std::dec;
            } else {
                out << static_cast<char>(ch);
            }
        }
    }
    return out.str();
}

std::string quoted(const std::string_view value) {
    return "\"" + json_escape(value) + "\"";
}

std::string utc_now() {
    const auto now = std::chrono::system_clock::now();
    const auto time = std::chrono::system_clock::to_time_t(now);
    std::tm utc{};
#ifdef _WIN32
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif
    std::ostringstream out;
    out << std::put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
    return out.str();
}

std::uint64_t working_set_bytes() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS_EX counters{};
    counters.cb = sizeof(counters);
    if (GetProcessMemoryInfo(GetCurrentProcess(),
                             reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&counters),
                             sizeof(counters))) {
        return static_cast<std::uint64_t>(counters.WorkingSetSize);
    }
    return 0;
#else
    rusage usage{};
    if (getrusage(RUSAGE_SELF, &usage) != 0) {
        return 0;
    }
#if defined(__APPLE__)
    return static_cast<std::uint64_t>(usage.ru_maxrss);
#else
    return static_cast<std::uint64_t>(usage.ru_maxrss) * 1024U;
#endif
#endif
}

std::string process_architecture() {
#if defined(_M_ARM64) || defined(__aarch64__)
    return "arm64";
#elif defined(_M_X64) || defined(__x86_64__)
    return "x86_64";
#else
    return "unknown";
#endif
}

std::string trim_text(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n\0");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n\0");
    return value.substr(first, last - first + 1);
}

#ifdef _WIN32
std::string registry_text(const char* key, const char* value) {
    DWORD bytes = 0;
    const auto measured = RegGetValueA(
        HKEY_LOCAL_MACHINE, key, value, RRF_RT_REG_SZ, nullptr, nullptr, &bytes);
    if (measured != ERROR_SUCCESS || bytes == 0) return {};
    std::vector<char> buffer(bytes, '\0');
    const auto loaded = RegGetValueA(
        HKEY_LOCAL_MACHINE, key, value, RRF_RT_REG_SZ, nullptr, buffer.data(),
        &bytes);
    if (loaded != ERROR_SUCCESS) return {};
    return trim_text(std::string(buffer.data()));
}

std::string host_processor() {
    return registry_text(
        "HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",
        "ProcessorNameString");
}

std::string system_product_name() {
    return registry_text("HARDWARE\\DESCRIPTION\\System\\BIOS",
                         "SystemProductName");
}
#else
std::string first_line(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::string line;
    return std::getline(input, line) ? trim_text(line) : std::string{};
}

std::string host_processor() {
    std::ifstream input("/proc/cpuinfo");
    std::string line;
    while (std::getline(input, line)) {
        const auto separator = line.find(':');
        if (separator == std::string::npos) continue;
        const auto key = trim_text(line.substr(0, separator));
        if (key == "model name" || key == "Hardware" || key == "Processor") {
            const auto value = trim_text(line.substr(separator + 1));
            if (!value.empty()) return value;
        }
    }
    return {};
}

std::string system_product_name() {
    return first_line("/sys/class/dmi/id/product_name");
}
#endif

std::string verified_runtime_value(const char* value,
                                   const std::string_view label) {
    const auto text = trim_text(value ? value : "");
    std::string lower = text;
    std::transform(lower.begin(), lower.end(), lower.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    if (text.empty() || lower == "unknown") {
        throw std::runtime_error(std::string(label) +
                                 " is unavailable; refusing unattested evidence");
    }
    if (text.size() > 256U ||
        !std::all_of(text.begin(), text.end(), [](const unsigned char ch) {
            return ch >= 0x20U && ch <= 0x7eU;
        })) {
        throw std::runtime_error(std::string(label) +
                                 " is not bounded printable ASCII");
    }
    return text;
}

bool safe_label(const std::string_view value) {
    return !value.empty() && value.size() <= 64U &&
           std::all_of(value.begin(), value.end(), [](const unsigned char ch) {
               return std::isalnum(ch) || ch == '.' || ch == '_' || ch == '-';
           });
}

std::string classified_stop_reason(const char* raw, const bool cancelled,
                                   const int result_code) {
    if (cancelled) return "callback_cancelled";
    if (result_code != GENIEX_SUCCESS) return "error";
    const auto reason = trim_text(raw ? raw : "");
    for (const auto* allowed :
         {"eos", "length", "user", "stop_sequence", "context_length"}) {
        if (reason == allowed) return reason;
    }
    return "other";
}

void write_exclusive_file(const std::filesystem::path& path,
                          const std::string_view bytes) {
#ifdef _WIN32
    HANDLE handle = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr,
                                CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) {
        throw std::system_error(
            static_cast<int>(GetLastError()), std::system_category(),
            "exclusively create evidence temporary");
    }
    std::size_t offset = 0;
    try {
        while (offset < bytes.size()) {
            const auto remaining = bytes.size() - offset;
            const auto chunk = static_cast<DWORD>(
                std::min<std::size_t>(remaining, 1024U * 1024U));
            DWORD written = 0;
            if (!WriteFile(handle, bytes.data() + offset, chunk, &written,
                           nullptr) || written == 0) {
                throw std::system_error(
                    static_cast<int>(GetLastError()), std::system_category(),
                    "write evidence temporary");
            }
            offset += written;
        }
        if (!FlushFileBuffers(handle)) {
            throw std::system_error(
                static_cast<int>(GetLastError()), std::system_category(),
                "flush evidence temporary");
        }
    } catch (...) {
        CloseHandle(handle);
        throw;
    }
    if (!CloseHandle(handle)) {
        throw std::system_error(
            static_cast<int>(GetLastError()), std::system_category(),
            "close evidence temporary");
    }
#else
    int flags = O_WRONLY | O_CREAT | O_EXCL;
#ifdef O_CLOEXEC
    flags |= O_CLOEXEC;
#endif
#ifdef O_NOFOLLOW
    flags |= O_NOFOLLOW;
#endif
    const int fd = ::open(path.c_str(), flags, 0600);
    if (fd < 0) {
        throw std::system_error(errno, std::generic_category(),
                                "exclusively create evidence temporary");
    }
    std::size_t offset = 0;
    try {
        while (offset < bytes.size()) {
            const auto count = ::write(fd, bytes.data() + offset,
                                       bytes.size() - offset);
            if (count < 0) {
                if (errno == EINTR) continue;
                throw std::system_error(errno, std::generic_category(),
                                        "write evidence temporary");
            }
            if (count == 0) {
                throw std::runtime_error("zero-length evidence write");
            }
            offset += static_cast<std::size_t>(count);
        }
        if (::fsync(fd) != 0) {
            throw std::system_error(errno, std::generic_category(),
                                    "flush evidence temporary");
        }
    } catch (...) {
        ::close(fd);
        throw;
    }
    if (::close(fd) != 0) {
        throw std::system_error(errno, std::generic_category(),
                                "close evidence temporary");
    }
#endif
}

void publish_no_replace(const std::filesystem::path& temporary,
                        const std::filesystem::path& output) {
    std::error_code error;
    std::filesystem::create_hard_link(temporary, output, error);
    if (error) {
        throw std::system_error(error, "publish evidence without replacement");
    }
    std::filesystem::remove(temporary, error);
    if (error) {
        throw std::system_error(error, "remove published evidence temporary");
    }
}

std::string random_session() {
    std::random_device source;
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (int i = 0; i < 4; ++i) {
        out << std::setw(8) << static_cast<std::uint32_t>(source());
    }
    auto value = out.str();
    value.resize(32);
    return value;
}

[[noreturn]] void usage(const std::string_view problem = {},
                        const int exit_code = EXIT_FAILURE) {
    if (!problem.empty()) {
        std::cerr << "error: " << problem << "\n\n";
    }
    std::cerr
        << "brickkv-replay --model PATH --plugin qairt|llama_cpp [options]\n"
        << "  --tokenizer PATH\n"
        << "  --device cpu|gpu|npu|hybrid\n"
        << "  --mode reset|legacy-test|managed|all\n"
        << "  --trace append_only|planning_removed|invalid_deleted|context_pruning|verifier_detour|cancellation_decode|all\n"
        << "  --output PATH --context N --max-tokens N --append-turns N\n"
        << "  --cancel-after-tokens N --hardware-label TEXT --source-revision TEXT\n";
    std::exit(exit_code);
}

int parse_positive(const std::string& value, const std::string& name) {
    std::size_t consumed = 0;
    int parsed = 0;
    try {
        parsed = std::stoi(value, &consumed);
    } catch (...) {
        usage(name + " must be a positive integer");
    }
    if (consumed != value.size() || parsed <= 0) {
        usage(name + " must be a positive integer");
    }
    return parsed;
}

bool full_lowercase_revision(const std::string_view value) {
    if (value.size() != 40 && value.size() != 64) {
        return false;
    }
    return std::all_of(value.begin(), value.end(), [](const char ch) {
        return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
    });
}

Options parse_options(const int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string key = argv[i];
        if (key == "--help" || key == "-h") {
            usage({}, EXIT_SUCCESS);
        }
        if (i + 1 >= argc) {
            usage("missing value for " + key);
        }
        const std::string value = argv[++i];
        if (key == "--model") options.model = value;
        else if (key == "--tokenizer") options.tokenizer = value;
        else if (key == "--output") options.output = value;
        else if (key == "--plugin") options.plugin = value;
        else if (key == "--device") options.device = value;
        else if (key == "--mode") options.mode = value;
        else if (key == "--trace") options.trace = value;
        else if (key == "--hardware-label") options.hardware_label = value;
        else if (key == "--source-revision") options.source_revision = value;
        else if (key == "--context") options.context = parse_positive(value, key);
        else if (key == "--max-tokens") options.max_tokens = parse_positive(value, key);
        else if (key == "--append-turns") options.append_turns = parse_positive(value, key);
        else if (key == "--cancel-after-tokens") {
            options.cancel_after_tokens = parse_positive(value, key);
        } else {
            usage("unknown option " + key);
        }
    }
    if (options.model.empty() || options.plugin.empty() ||
        options.output.empty() || options.hardware_label.empty() ||
        options.source_revision.empty()) {
        usage("--model, --plugin, --output, --hardware-label, and "
              "--source-revision are required");
    }
    if (!full_lowercase_revision(options.source_revision)) {
        usage("--source-revision must be a full lowercase Git object ID");
    }
    if (!safe_label(options.hardware_label)) {
        usage("--hardware-label must contain 1-64 letters, digits, '.', '_', or '-'");
    }
    if (std::filesystem::exists(options.output)) {
        usage("refusing to overwrite evidence output " +
              options.output.string());
    }
    const std::vector<std::string> plugins{"qairt", "llama_cpp"};
    if (std::find(plugins.begin(), plugins.end(), options.plugin) ==
        plugins.end()) {
        usage("--plugin must be qairt or llama_cpp");
    }
    const std::vector<std::string> devices{"cpu", "gpu", "npu", "hybrid"};
    if (std::find(devices.begin(), devices.end(), options.device) ==
        devices.end()) {
        usage("--device must be cpu, gpu, npu, or hybrid");
    }
    const std::vector<std::string> modes{
        "reset", "legacy-test", "managed", "all"};
    if (std::find(modes.begin(), modes.end(), options.mode) == modes.end()) {
        usage("unknown mode " + options.mode);
    }
    const std::vector<std::string> traces{
        "append_only", "planning_removed", "invalid_deleted",
        "context_pruning", "verifier_detour", "cancellation_decode", "all"};
    if (std::find(traces.begin(), traces.end(), options.trace) == traces.end()) {
        usage("unknown trace " + options.trace);
    }
    return options;
}

void require_success(const int code, const std::string_view operation) {
    if (code == GENIEX_SUCCESS) {
        return;
    }
    const char* message = geniex_get_error_message(
        static_cast<geniex_ErrorCode>(code));
    throw std::runtime_error(std::string(operation) + " failed (" +
                             std::to_string(code) + "): " +
                             (message ? message : "unknown error"));
}

class Runtime {
  public:
    Runtime() { require_success(geniex_init(), "geniex_init"); }
    ~Runtime() { geniex_deinit(); }
    Runtime(const Runtime&) = delete;
    Runtime& operator=(const Runtime&) = delete;
};

class Model {
  public:
    explicit Model(const Options& options) {
        model_path_ = options.model.string();
        tokenizer_path_ = options.tokenizer.string();
        plugin_ = options.plugin;
        geniex_ResolveDeviceInput device_input{};
        device_input.plugin_id = options.plugin.c_str();
        device_input.model_name = model_path_.c_str();
        device_input.mode = options.device.c_str();
        device_input.ngl_default = -1;
        geniex_ResolveDeviceOutput device_output{};
        require_success(geniex_resolve_device(&device_input, &device_output),
                        "geniex_resolve_device");
        if (device_output.device_id) {
            device_id_ = device_output.device_id;
            geniex_free(device_output.device_id);
        }
        if (device_output.warning) {
            device_warning_ = device_output.warning;
            geniex_free(device_output.warning);
        }
        geniex_LlmCreateInput input{};
        input.model_path = model_path_.c_str();
        input.tokenizer_path = tokenizer_path_.empty() ? nullptr : tokenizer_path_.c_str();
        input.plugin_id = plugin_.c_str();
        input.device_id = device_id_.empty() ? nullptr : device_id_.c_str();
        runtime_n_ctx_ = brickkv::runtime_n_ctx(options.plugin, options.context);
        input.config.n_ctx = runtime_n_ctx_;
        input.config.n_gpu_layers = device_output.ngl;
        require_success(geniex_llm_create(&input, &handle_), "geniex_llm_create");
    }

    ~Model() {
        if (handle_) {
            geniex_llm_destroy(handle_);
        }
    }
    Model(const Model&) = delete;
    Model& operator=(const Model&) = delete;

    void reset() { require_success(geniex_llm_reset(handle_), "geniex_llm_reset"); }
    geniex_LLM* get() const { return handle_; }
    const std::string& resolved_device() const { return device_id_; }
    const std::string& device_warning() const { return device_warning_; }
    int runtime_n_ctx() const { return runtime_n_ctx_; }

  private:
    geniex_LLM* handle_ = nullptr;
    std::string model_path_;
    std::string tokenizer_path_;
    std::string plugin_;
    std::string device_id_;
    std::string device_warning_;
    int runtime_n_ctx_ = 0;
};

struct CallbackState {
    int seen = 0;
    int cancel_after = 0;
    bool cancelled = false;
};

bool token_callback(const char*, void* opaque) {
    auto& state = *static_cast<CallbackState*>(opaque);
    ++state.seen;
    if (state.cancel_after > 0 && state.seen >= state.cancel_after) {
        state.cancelled = true;
        return false;
    }
    return true;
}

std::string apply_template(geniex_LLM* model,
                           const std::vector<Message>& messages) {
    std::vector<geniex_LlmChatMessage> native;
    native.reserve(messages.size());
    for (const auto& message : messages) {
        native.push_back({message.role.c_str(), message.content.c_str()});
    }
    geniex_LlmApplyChatTemplateInput input{};
    input.messages = native.data();
    input.message_count = static_cast<std::int32_t>(native.size());
    input.enable_thinking = false;
    input.add_generation_prompt = true;
    geniex_LlmApplyChatTemplateOutput output{};
    require_success(geniex_llm_apply_chat_template(model, &input, &output),
                    "geniex_llm_apply_chat_template");
    std::unique_ptr<char, decltype(&geniex_free)> text(output.formatted_text,
                                                       &geniex_free);
    if (!text) {
        throw std::runtime_error("chat template returned no text");
    }
    return text.get();
}

Generation generate(Model& model, const Options& options,
                    const std::vector<Message>& messages, const bool cancel) {
    const auto prompt = apply_template(model.get(), messages);
    geniex_SamplerConfig sampler{};
    sampler.temperature = 0.0F;
    sampler.top_p = 1.0F;
    sampler.seed = 42;
    geniex_GenerationConfig config{};
    config.max_tokens = options.max_tokens;
    config.sampler_config = &sampler;
    CallbackState callback{};
    callback.cancel_after = cancel ? options.cancel_after_tokens : 0;
    geniex_LlmGenerateInput input{};
    input.prompt_utf8 = prompt.c_str();
    input.config = &config;
    input.on_token = &token_callback;
    input.user_data = &callback;
    geniex_LlmGenerateOutput output{};
    const auto started = std::chrono::steady_clock::now();
    const auto code = geniex_llm_generate(model.get(), &input, &output);
    const auto ended = std::chrono::steady_clock::now();
    std::unique_ptr<char, decltype(&geniex_free)> full_text(output.full_text,
                                                            &geniex_free);

    Record record;
    record.result_code = code;
    record.ttft_us = output.profile_data.ttft;
    record.prompt_us = output.profile_data.prompt_time;
    record.decode_us = output.profile_data.decode_time;
    record.prompt_tokens = output.profile_data.prompt_tokens;
    record.generated_tokens = output.profile_data.generated_tokens;
    record.wall_us = std::chrono::duration_cast<std::chrono::microseconds>(
                         ended - started)
                         .count();
    record.working_set_bytes = working_set_bytes();
    record.callback_cancelled = callback.cancelled;
    record.stop_reason = classified_stop_reason(
        output.profile_data.stop_reason, callback.cancelled, code);
    const std::string text = full_text ? full_text.get() : "";
    record.output_digest = "sha256:" + brickkv::sha256(text);
    if (code != GENIEX_SUCCESS && !callback.cancelled) {
        require_success(code, "geniex_llm_generate");
    }
    return Generation{std::move(record), text};
}

std::vector<std::string> selected_modes(const std::string& requested) {
    if (requested == "all") return {"reset", "legacy-test", "managed"};
    return {requested};
}

std::vector<std::string> selected_traces(const std::string& requested) {
    if (requested == "all") {
        return {"append_only", "planning_removed", "invalid_deleted",
                "context_pruning", "verifier_detour", "cancellation_decode"};
    }
    return {requested};
}

std::vector<Message> initial_messages(const std::string& trace) {
    return {
        {"system", "Use only the synthetic facts in this conversation."},
        {"user", "Summarize synthetic request 1 for trace " + trace + "."},
    };
}

std::string next_user(const std::string& trace, const int step) {
    return "Continue synthetic trace " + trace + " at step " +
           std::to_string(step + 1) + ".";
}

std::vector<Record> run_trace(Model& model, const Options& options,
                              const Identity& identity, const std::string& mode,
                              const std::string& trace) {
    model.reset();
    std::uint64_t generation = 1;
    LineageGate gate;
    const auto driver_session = random_session();
    const auto verifier_session = random_session();
    std::map<std::string, std::string> parents{{"driver", ""}, {"verifier", ""}};
    std::map<std::string, std::vector<Message>> transcripts{
        {"driver", initial_messages(trace)},
        {"verifier", {{"system", "Check only synthetic evidence."},
                      {"user", "Verify the synthetic draft without changing it."}}},
    };
    std::vector<Record> records;
    const int steps = trace == "append_only" ? options.append_turns :
                      trace == "verifier_detour" ? 3 : 4;
    for (int step = 0; step < steps; ++step) {
        std::string role = "driver";
        if (trace == "verifier_detour" && step == 1) role = "verifier";
        auto& messages = transcripts.at(role);

        if ((trace == "planning_removed" || trace == "invalid_deleted") &&
            step == 2 && messages.size() >= 6) {
            messages.erase(messages.begin() + 3, messages.begin() + 5);
        } else if (trace == "context_pruning" && step == 2) {
            messages = {{"system", "Use only the approved synthetic summary."},
                        {"user", "Continue after deterministic context pruning."}};
        }

        bool cancel = trace == "cancellation_decode" && step == 1;
        std::uint64_t transaction = 0;
        std::string status = mode == "legacy-test" ? "legacy-test" : "reset";
        std::string reason = mode == "legacy-test" ? "raw_keep_cache" : "reset_each_call";
        if (mode == "reset") {
            model.reset();
            ++generation;
        } else if (mode == "managed") {
            Request request{
                role == "driver" ? driver_session : verifier_session,
                parents.at(role), identity, messages};
            auto decision = gate.begin(request, generation);
            transaction = decision.transaction;
            if (!decision.reuse) {
                model.reset();
                ++generation;
            }
            decision = gate.bind_generation(transaction, generation);
            status = decision.status;
            reason = decision.reason;
        }

        Generation generated{};
        try {
            generated = generate(model, options, messages, cancel);
        } catch (...) {
            if (mode == "managed") gate.abort(transaction);
            model.reset();
            ++generation;
            throw;
        }
        Record& record = generated.record;
        record.trace = trace;
        record.mode = mode;
        record.role = role;
        record.step = step;
        record.cache_status = status;
        record.cache_reason = reason;

        if (cancel && !record.callback_cancelled) {
            if (mode == "managed") gate.abort(transaction);
            model.reset();
            ++generation;
            throw std::runtime_error(
                "cancellation trace completed without exercising the token callback");
        }

        if (cancel) {
            record.cache_status = "aborted";
            record.cache_reason = "callback_cancellation";
            if (mode == "managed") gate.abort(transaction);
            model.reset();
            ++generation;
            if (!messages.empty()) {
                messages.back().content =
                    "Retry the interrupted synthetic task from a clean state.";
            }
            records.push_back(std::move(generated.record));
            continue;
        }

        if (mode == "managed") {
            const auto metadata = gate.commit(transaction, generated.text);
            parents.at(role) = metadata.revision;
            record.revision = metadata.revision;
            messages.push_back({"assistant", generated.text});
        } else {
            messages.push_back({"assistant", generated.text});
        }
        if (!(trace == "verifier_detour" && role == "verifier")) {
            messages.push_back({"user", next_user(trace, step)});
        }
        records.push_back(std::move(generated.record));
    }
    return records;
}

void write_evidence(const Options& options, const std::string& sdk_version,
                    const std::string& plugin_version,
                    const std::string& model_digest,
                    const std::string& tokenizer_digest,
                    const std::string& processor,
                    const std::string& product_name, const Model& model,
                    const std::vector<Record>& records) {
    const auto parent = options.output.parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent);
    }
    if (std::filesystem::exists(options.output)) {
        throw std::runtime_error("refusing to overwrite evidence output: " +
                                 options.output.string());
    }
    auto temporary = options.output;
    temporary += ".tmp";
    if (std::filesystem::exists(temporary)) {
        throw std::runtime_error("refusing to overwrite partial evidence: " +
                                 temporary.string());
    }
    std::ostringstream out;
    out << "{\n"
        << "  \"schema_version\": \"brickkv.replay/2\",\n"
        << "  \"status\": \"complete\",\n"
        << "  \"created_at\": " << quoted(utc_now()) << ",\n"
        << "  \"attestation\": {\n"
        << "    \"source_revision\": " << quoted(options.source_revision) << ",\n"
        << "    \"sdk_version\": " << quoted(sdk_version) << ",\n"
        << "    \"plugin\": " << quoted(options.plugin) << ",\n"
        << "    \"plugin_version\": " << quoted(plugin_version) << ",\n"
        << "    \"model_digest\": " << quoted(model_digest) << ",\n"
        << "    \"tokenizer_digest\": " << quoted(tokenizer_digest) << ",\n"
        << "    \"requested_device\": " << quoted(options.device) << ",\n"
        << "    \"resolved_device\": " << quoted(model.resolved_device()) << ",\n"
        << "    \"device_warning\": "
        << quoted(model.device_warning().empty() ? "none" : "present") << ",\n"
        << "    \"hardware_label\": " << quoted(options.hardware_label) << ",\n"
        << "    \"process_architecture\": " << quoted(process_architecture()) << ",\n"
        << "    \"host_processor\": " << quoted(processor) << ",\n"
        << "    \"system_product_name\": " << quoted(product_name) << "\n"
        << "  },\n"
        << "  \"configuration\": {\"context\": " << options.context
        << ", \"runtime_n_ctx\": " << model.runtime_n_ctx()
        << ", \"max_tokens\": " << options.max_tokens
        << ", \"append_turns\": " << options.append_turns
        << ", \"cancel_after_tokens\": " << options.cancel_after_tokens << "},\n"
        << "  \"records\": [\n";
    for (std::size_t i = 0; i < records.size(); ++i) {
        const auto& record = records[i];
        out << "    {\"trace\": " << quoted(record.trace)
            << ", \"mode\": " << quoted(record.mode)
            << ", \"role\": " << quoted(record.role)
            << ", \"step\": " << record.step
            << ", \"cache_status\": " << quoted(record.cache_status)
            << ", \"cache_reason\": " << quoted(record.cache_reason)
            << ", \"revision\": " << quoted(record.revision)
            << ", \"result_code\": " << record.result_code
            << ", \"stop_reason\": " << quoted(record.stop_reason)
            << ", \"callback_cancelled\": "
            << (record.callback_cancelled ? "true" : "false")
            << ", \"ttft_us\": " << record.ttft_us
            << ", \"prompt_us\": " << record.prompt_us
            << ", \"decode_us\": " << record.decode_us
            << ", \"wall_us\": " << record.wall_us
            << ", \"prompt_tokens\": " << record.prompt_tokens
            << ", \"generated_tokens\": " << record.generated_tokens
            << ", \"working_set_bytes\": " << record.working_set_bytes
            << ", \"output_digest\": " << quoted(record.output_digest) << "}"
            << (i + 1 == records.size() ? "\n" : ",\n");
    }
    out << "  ]\n}\n";
    const auto payload = out.str();
    write_exclusive_file(temporary, payload);
    publish_no_replace(temporary, options.output);
}

}  // namespace

int main(const int argc, char** argv) {
    try {
        auto options = parse_options(argc, argv);
        if (std::filesystem::is_symlink(
                std::filesystem::symlink_status(options.model))) {
            throw std::runtime_error("model root must not be a symbolic link");
        }
        options.model = std::filesystem::canonical(options.model);
        if (!options.tokenizer.empty()) {
            if (std::filesystem::is_symlink(
                    std::filesystem::symlink_status(options.tokenizer))) {
                throw std::runtime_error(
                    "tokenizer root must not be a symbolic link");
            }
            options.tokenizer = std::filesystem::canonical(options.tokenizer);
        }
        const auto model_digest = brickkv::sha256_file_tree(options.model);
        const auto tokenizer_digest = options.tokenizer.empty()
                                          ? std::string("none")
                                          : brickkv::sha256_file_tree(options.tokenizer);
        Runtime runtime;
        const std::string sdk_version =
            verified_runtime_value(geniex_version(), "GenieX SDK version");
        const std::string plugin_version = verified_runtime_value(
            geniex_get_plugin_version(options.plugin.c_str()),
            "GenieX plugin version");
        const auto processor = verified_runtime_value(
            host_processor().c_str(), "host processor identity");
        const auto product_name = verified_runtime_value(
            system_product_name().c_str(), "system product identity");
        Model model(options);
        if (brickkv::sha256_file_tree(options.model) != model_digest ||
            (!options.tokenizer.empty() &&
             brickkv::sha256_file_tree(options.tokenizer) != tokenizer_digest)) {
            throw std::runtime_error(
                "model or tokenizer changed while GenieX loaded it");
        }
        const Identity identity{
            model_digest, tokenizer_digest, options.plugin, plugin_version,
            model.resolved_device(), "sdk-native", "temperature=0;seed=42"};

        std::vector<Record> records;
        for (const auto& mode : selected_modes(options.mode)) {
            for (const auto& trace : selected_traces(options.trace)) {
                auto trace_records =
                    run_trace(model, options, identity, mode, trace);
                records.insert(records.end(),
                               std::make_move_iterator(trace_records.begin()),
                               std::make_move_iterator(trace_records.end()));
            }
        }
        if (brickkv::sha256_file_tree(options.model) != model_digest ||
            (!options.tokenizer.empty() &&
             brickkv::sha256_file_tree(options.tokenizer) != tokenizer_digest)) {
            throw std::runtime_error(
                "model or tokenizer changed during the replay study");
        }
        write_evidence(options, sdk_version, plugin_version, model_digest,
                       tokenizer_digest, processor, product_name, model,
                       records);
        std::cout << "wrote " << records.size() << " secret-free records to "
                  << options.output << '\n';
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "brickkv-replay: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
