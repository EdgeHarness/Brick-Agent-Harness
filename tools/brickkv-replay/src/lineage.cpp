#include "brickkv/lineage.hpp"

#include <algorithm>
#include <stdexcept>

namespace brickkv {

bool valid_session(std::string_view value) {
    return value.size() == 32 &&
           std::all_of(value.begin(), value.end(), [](const char ch) {
               return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
           });
}

bool valid_revision(std::string_view value) {
    if (value.size() != 71 || value.substr(0, 7) != "sha256:") {
        return false;
    }
    return std::all_of(value.begin() + 7, value.end(), [](const char ch) {
        return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
    });
}

bool strict_extension(const std::vector<Message>& prefix,
                      const std::vector<Message>& candidate) {
    return candidate.size() > prefix.size() &&
           std::equal(prefix.begin(), prefix.end(), candidate.begin());
}

Decision LineageGate::begin(const Request& request,
                            const std::uint64_t model_generation) {
    if (!valid_session(request.session)) {
        throw std::invalid_argument("session must be 32 lowercase hexadecimal characters");
    }
    if (!request.parent.empty() && !valid_revision(request.parent)) {
        throw std::invalid_argument("parent must be empty or sha256:<64 lowercase hex>");
    }
    if (request.messages.empty()) {
        throw std::invalid_argument("a managed request requires messages");
    }
    for (const auto& message : request.messages) {
        if (message.role != "system" && message.role != "user" &&
            message.role != "assistant") {
            throw std::invalid_argument(
                "managed replay accepts system, user, and assistant text messages only");
        }
    }

    if (pending_) {
        pending_.reset();
        committed_.reset();
    }
    Decision decision{++next_transaction_, false, true, "reset", "branch"};
    if (committed_ && !committed_->reusable) {
        // A non-reusable commit is reset immediately. Keep its logical parent
        // long enough to explain the next cold decision without resetting the
        // already-clean model a second time.
        decision.reset_required = false;
    }
    if (!committed_ && request.parent.empty()) {
        decision.status = "cold";
        decision.reason = "first_request";
    } else if (!committed_) {
        decision.reason = "parent_mismatch";
    } else if (committed_->session != request.session) {
        decision.reason = "session_switch";
    } else if (committed_->identity != request.identity) {
        decision.reason = "branch";
    } else if (committed_->revision != request.parent) {
        decision.reason = "parent_mismatch";
    } else if (strict_extension(committed_->messages, request.messages)) {
        if (!committed_->reusable) {
            decision.reason = "previous_not_reusable";
        } else if (committed_->generation != model_generation) {
            decision.reason = "parent_mismatch";
        } else {
            decision.reuse = true;
            decision.reset_required = false;
            decision.status = "reused";
            decision.reason = "exact_extension";
        }
    }
    if (!decision.reuse) {
        committed_.reset();
    }
    pending_ = Pending{decision.transaction, request, decision, model_generation};
    return decision;
}

Decision LineageGate::bind_generation(const std::uint64_t transaction,
                                      const std::uint64_t model_generation) {
    if (!pending_ || pending_->transaction != transaction) {
        throw std::logic_error("managed cache transaction is not active");
    }
    if (pending_->decision.reuse &&
        (!committed_ || committed_->generation != model_generation)) {
        committed_.reset();
        pending_->decision.reuse = false;
        pending_->decision.reset_required = true;
        pending_->decision.status = "reset";
        pending_->decision.reason = "parent_mismatch";
    }
    pending_->generation = model_generation;
    return pending_->decision;
}

Metadata LineageGate::commit(const std::uint64_t transaction,
                             const std::string_view assistant,
                             const bool reusable) {
    if (!pending_ || pending_->transaction != transaction) {
        throw std::logic_error("managed cache transaction is not active");
    }
    auto messages = pending_->request.messages;
    messages.push_back(Message{"assistant", std::string(assistant)});
    const auto revision = transcript_revision(pending_->request.identity, messages);
    const auto metadata = Metadata{pending_->decision.status,
                                   pending_->decision.reason, revision,
                                   reusable};
    committed_ = Committed{pending_->request.session, revision,
                           pending_->request.identity, std::move(messages),
                           pending_->generation, reusable};
    pending_.reset();
    return metadata;
}

void LineageGate::abort(const std::uint64_t transaction) {
    if (pending_ && pending_->transaction == transaction) {
        pending_.reset();
    }
    committed_.reset();
}

void LineageGate::clear() {
    pending_.reset();
    committed_.reset();
}

}  // namespace brickkv
