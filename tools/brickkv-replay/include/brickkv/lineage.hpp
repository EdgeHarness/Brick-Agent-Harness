#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace brickkv {

struct Message {
    std::string role;
    std::string content;

    bool operator==(const Message&) const = default;
};

struct Identity {
    std::string model_digest;
    std::string tokenizer_digest;
    std::string runtime;
    std::string runtime_version;
    std::string device;
    std::string chat_template;
    std::string options;

    bool operator==(const Identity&) const = default;
};

struct Request {
    std::string session;
    std::string parent;
    Identity identity;
    std::vector<Message> messages;
};

struct Decision {
    std::uint64_t transaction = 0;
    bool reuse = false;
    std::string status;
    std::string reason;
};

struct Metadata {
    std::string status;
    std::string reason;
    std::string revision;
};

// A small, sequential reference implementation used by brickkv-replay. It is
// deliberately independent of the GenieX server implementation: the replay
// tool can therefore catch unsafe behavior in the runtime instead of trusting
// the component under test to describe its own state correctly.
class LineageGate {
  public:
    Decision begin(const Request& request, std::uint64_t model_generation);
    Decision bind_generation(std::uint64_t transaction,
                             std::uint64_t model_generation);
    Metadata commit(std::uint64_t transaction, std::string_view assistant);
    void abort(std::uint64_t transaction);
    void clear();

  private:
    struct Committed {
        std::string session;
        std::string revision;
        Identity identity;
        std::vector<Message> messages;
        std::uint64_t generation = 0;
    };
    struct Pending {
        std::uint64_t transaction = 0;
        Request request;
        Decision decision;
        std::uint64_t generation = 0;
    };

    std::uint64_t next_transaction_ = 0;
    std::optional<Committed> committed_;
    std::optional<Pending> pending_;
};

bool strict_extension(const std::vector<Message>& prefix,
                      const std::vector<Message>& candidate);
bool valid_session(std::string_view value);
bool valid_revision(std::string_view value);
std::string transcript_revision(const Identity& identity,
                                const std::vector<Message>& messages);
std::string sha256(std::string_view bytes);
std::string sha256_file_tree(const std::filesystem::path& root);

}  // namespace brickkv
