#include "brickkv/lineage.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace brickkv {
namespace {

constexpr std::array<std::uint32_t, 64> kRound = {
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
    0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
    0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
    0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
    0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
    0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
    0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
    0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
    0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
    0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
    0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
    0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
    0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
    0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
    0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
    0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
};

class Sha256State {
  public:
    void update(const void* raw, std::size_t size) {
        const auto* bytes = static_cast<const std::uint8_t*>(raw);
        total_bytes_ += size;
        while (size > 0) {
            const auto count = std::min(size, block_.size() - block_size_);
            std::copy_n(bytes, count, block_.begin() +
                                      static_cast<std::ptrdiff_t>(block_size_));
            bytes += count;
            size -= count;
            block_size_ += count;
            if (block_size_ == block_.size()) {
                transform(block_.data());
                block_size_ = 0;
            }
        }
    }

    void update(const std::string_view value) { update(value.data(), value.size()); }

    std::string finish() {
        const auto bit_length = static_cast<std::uint64_t>(total_bytes_) * 8U;
        block_[block_size_++] = 0x80U;
        if (block_size_ > 56U) {
            std::fill(block_.begin() + static_cast<std::ptrdiff_t>(block_size_),
                      block_.end(), std::uint8_t{0});
            transform(block_.data());
            block_size_ = 0;
        }
        std::fill(block_.begin() + static_cast<std::ptrdiff_t>(block_size_),
                  block_.begin() + 56, std::uint8_t{0});
        for (int shift = 56; shift >= 0; shift -= 8) {
            block_[56U + static_cast<std::size_t>((56 - shift) / 8)] =
                static_cast<std::uint8_t>((bit_length >> shift) & 0xffU);
        }
        transform(block_.data());

        std::ostringstream output;
        output << std::hex << std::setfill('0');
        for (const auto value : state_) {
            output << std::setw(8) << value;
        }
        return output.str();
    }

  private:
    void transform(const std::uint8_t* block) {
        std::array<std::uint32_t, 64> words{};
        for (std::size_t i = 0; i < 16; ++i) {
            const auto offset = i * 4U;
            words[i] = (static_cast<std::uint32_t>(block[offset]) << 24U) |
                       (static_cast<std::uint32_t>(block[offset + 1]) << 16U) |
                       (static_cast<std::uint32_t>(block[offset + 2]) << 8U) |
                       static_cast<std::uint32_t>(block[offset + 3]);
        }
        for (std::size_t i = 16; i < words.size(); ++i) {
            const auto s0 = std::rotr(words[i - 15], 7) ^
                            std::rotr(words[i - 15], 18) ^
                            (words[i - 15] >> 3U);
            const auto s1 = std::rotr(words[i - 2], 17) ^
                            std::rotr(words[i - 2], 19) ^
                            (words[i - 2] >> 10U);
            words[i] = words[i - 16] + s0 + words[i - 7] + s1;
        }

        auto a = state_[0];
        auto b = state_[1];
        auto c = state_[2];
        auto d = state_[3];
        auto e = state_[4];
        auto f = state_[5];
        auto g = state_[6];
        auto h = state_[7];
        for (std::size_t i = 0; i < words.size(); ++i) {
            const auto sum1 = std::rotr(e, 6) ^ std::rotr(e, 11) ^ std::rotr(e, 25);
            const auto choose = (e & f) ^ ((~e) & g);
            const auto temp1 = h + sum1 + choose + kRound[i] + words[i];
            const auto sum0 = std::rotr(a, 2) ^ std::rotr(a, 13) ^ std::rotr(a, 22);
            const auto majority = (a & b) ^ (a & c) ^ (b & c);
            const auto temp2 = sum0 + majority;
            h = g;
            g = f;
            f = e;
            e = d + temp1;
            d = c;
            c = b;
            b = a;
            a = temp1 + temp2;
        }
        state_[0] += a;
        state_[1] += b;
        state_[2] += c;
        state_[3] += d;
        state_[4] += e;
        state_[5] += f;
        state_[6] += g;
        state_[7] += h;
    }

    std::array<std::uint32_t, 8> state_ = {
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
    };
    std::array<std::uint8_t, 64> block_{};
    std::size_t block_size_ = 0;
    std::uint64_t total_bytes_ = 0;
};

void update_u64(Sha256State& state, const std::uint64_t value) {
    std::array<std::uint8_t, 8> bytes{};
    for (int shift = 56; shift >= 0; shift -= 8) {
        bytes[static_cast<std::size_t>((56 - shift) / 8)] =
            static_cast<std::uint8_t>((value >> shift) & 0xffU);
    }
    state.update(bytes.data(), bytes.size());
}

void update_frame(Sha256State& state, const std::string_view value) {
    update_u64(state, value.size());
    state.update(value);
}

std::string path_text(const std::filesystem::path& value) {
    return value.generic_string();
}

}  // namespace

std::string sha256(const std::string_view bytes) {
    Sha256State state;
    state.update(bytes);
    return state.finish();
}

std::string sha256_file_bytes(const std::filesystem::path& path) {
    namespace fs = std::filesystem;
    const auto status = fs::symlink_status(path);
    if (!fs::is_regular_file(status) || fs::is_symlink(status)) {
        throw std::runtime_error(
            "artifact must be one regular non-link file: " + path_text(path));
    }
    const auto expected_size = fs::file_size(path);
    const auto expected_write_time = fs::last_write_time(path);
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("cannot open artifact file: " + path_text(path));
    }
    Sha256State state;
    std::vector<char> buffer(1024U * 1024U);
    std::uintmax_t observed_size = 0;
    while (input) {
        input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto count = input.gcount();
        if (count > 0) {
            state.update(buffer.data(), static_cast<std::size_t>(count));
            observed_size += static_cast<std::uintmax_t>(count);
        }
    }
    if (!input.eof()) {
        throw std::runtime_error("failed while reading artifact file: " + path_text(path));
    }
    const auto after_status = fs::symlink_status(path);
    if (!fs::is_regular_file(after_status) || fs::is_symlink(after_status) ||
        observed_size != expected_size || fs::file_size(path) != expected_size ||
        fs::last_write_time(path) != expected_write_time) {
        throw std::runtime_error("artifact changed while hashing: " + path_text(path));
    }
    return "sha256:" + state.finish();
}

std::string runtime_bundle_digest(
    const std::vector<std::filesystem::path>& artifacts) {
    if (artifacts.empty()) {
        throw std::runtime_error("at least one runtime artifact is required");
    }
    std::vector<std::pair<std::string, std::string>> entries;
    for (const auto& path : artifacts) {
        auto name = path.filename().string();
        std::transform(name.begin(), name.end(), name.begin(), [](unsigned char ch) {
            return static_cast<char>(std::tolower(ch));
        });
        if (name.empty() || name.size() > 128U ||
            !std::all_of(name.begin(), name.end(), [](const unsigned char ch) {
                return std::isalnum(ch) || ch == '.' || ch == '_' || ch == '+' ||
                       ch == '-';
            })) {
            throw std::runtime_error("runtime artifact has an unsafe file name");
        }
        entries.emplace_back(std::move(name), sha256_file_bytes(path));
    }
    std::sort(entries.begin(), entries.end());
    for (std::size_t i = 1; i < entries.size(); ++i) {
        if (entries[i - 1].first == entries[i].first) {
            throw std::runtime_error("runtime artifact file names must be unique");
        }
    }
    std::string material("brickkv-runtime-bundle/1\0", 25);
    for (const auto& [name, digest] : entries) {
        material.append(name);
        material.push_back('\0');
        material.append(digest);
        material.push_back('\0');
    }
    return "sha256:" + sha256(material);
}

std::string transcript_revision(const Identity& identity,
                                const std::vector<Message>& messages) {
    Sha256State state;
    state.update(std::string_view("brickkv-replay-lineage/2\0", 25));
    for (const auto* field : {&identity.model_digest, &identity.tokenizer_digest,
                              &identity.runtime, &identity.runtime_version,
                              &identity.device, &identity.chat_template,
                              &identity.options}) {
        update_frame(state, *field);
    }
    update_u64(state, messages.size());
    for (const auto& message : messages) {
        update_frame(state, message.role);
        update_frame(state, message.content);
    }
    return "sha256:" + state.finish();
}

std::string sha256_file_tree(const std::filesystem::path& root) {
    namespace fs = std::filesystem;
    if (!fs::exists(root) || fs::is_symlink(fs::symlink_status(root))) {
        throw std::runtime_error("artifact is missing or is a symbolic link: " + path_text(root));
    }

    std::vector<std::pair<fs::path, fs::path>> files;
    const bool root_is_file = fs::is_regular_file(root);
    if (root_is_file) {
        files.emplace_back(root.filename(), root);
    } else if (fs::is_directory(root)) {
        for (const auto& entry : fs::recursive_directory_iterator(root)) {
            const auto status = entry.symlink_status();
            if (fs::is_symlink(status)) {
                throw std::runtime_error("symbolic links are not accepted in artifacts: " +
                                         path_text(entry.path()));
            }
            if (fs::is_regular_file(status)) {
                files.emplace_back(fs::relative(entry.path(), root), entry.path());
            } else if (!fs::is_directory(status)) {
                throw std::runtime_error("artifact contains a non-regular entry: " +
                                         path_text(entry.path()));
            }
        }
    } else {
        throw std::runtime_error("artifact must be a regular file or directory: " +
                                 path_text(root));
    }
    if (files.empty()) {
        throw std::runtime_error("artifact contains no regular files: " + path_text(root));
    }
    std::sort(files.begin(), files.end(), [](const auto& left, const auto& right) {
        return path_text(left.first) < path_text(right.first);
    });

    Sha256State state;
    state.update(std::string_view("brickkv-replay-artifact/1\0", 26));
    update_frame(state, root_is_file ? "file" : "directory");
    update_u64(state, files.size());
    // Keep large artifact IO storage off the small Windows ARM64 thread stack.
    std::vector<char> buffer(1024U * 1024U);
    for (const auto& [relative, absolute] : files) {
        const auto before_status = fs::symlink_status(absolute);
        if (!fs::is_regular_file(before_status) || fs::is_symlink(before_status)) {
            throw std::runtime_error("artifact entry changed before hashing: " +
                                     path_text(absolute));
        }
        const auto expected_size = fs::file_size(absolute);
        const auto expected_write_time = fs::last_write_time(absolute);
        update_frame(state, path_text(relative));
        update_u64(state, expected_size);
        std::ifstream input(absolute, std::ios::binary);
        if (!input) {
            throw std::runtime_error("cannot open artifact file: " + path_text(absolute));
        }
        std::uintmax_t observed_size = 0;
        while (input) {
            input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
            const auto count = input.gcount();
            if (count > 0) {
                state.update(buffer.data(), static_cast<std::size_t>(count));
                observed_size += static_cast<std::uintmax_t>(count);
            }
        }
        if (!input.eof()) {
            throw std::runtime_error("failed while reading artifact file: " + path_text(absolute));
        }
        const auto after_status = fs::symlink_status(absolute);
        if (!fs::is_regular_file(after_status) || fs::is_symlink(after_status) ||
            observed_size != expected_size ||
            fs::file_size(absolute) != expected_size ||
            fs::last_write_time(absolute) != expected_write_time) {
            throw std::runtime_error("artifact entry changed while hashing: " +
                                     path_text(absolute));
        }
    }
    return "sha256:" + state.finish();
}

}  // namespace brickkv
