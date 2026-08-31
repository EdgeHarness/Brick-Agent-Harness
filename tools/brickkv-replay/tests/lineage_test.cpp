#include "brickkv/lineage.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using brickkv::Identity;
using brickkv::LineageGate;
using brickkv::Message;
using brickkv::Request;

constexpr auto kSessionA = "0123456789abcdef0123456789abcdef";
constexpr auto kSessionB = "fedcba9876543210fedcba9876543210";

void require(const bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

Request request(std::string parent, std::vector<Message> messages) {
    return Request{kSessionA, std::move(parent),
                   Identity{"model", "tokenizer", "qairt", "1", "NPU",
                            "template", "seed=42"},
                   std::move(messages)};
}

}  // namespace

int main() {
    try {
        require(brickkv::sha256("") ==
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "SHA-256 empty-string vector failed");
        require(brickkv::sha256("abc") ==
                    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                "SHA-256 abc vector failed");

        const auto fixture_root = std::filesystem::temp_directory_path() /
            ("brickkv-lineage-" + std::to_string(std::random_device{}()));
        std::filesystem::create_directories(fixture_root / "tree");
        {
            std::ofstream file(fixture_root / "artifact", std::ios::binary);
            file << "same-bytes";
        }
        {
            std::ofstream file(fixture_root / "tree" / "artifact",
                               std::ios::binary);
            file << "same-bytes";
        }
        require(brickkv::sha256_file_tree(fixture_root / "artifact") !=
                    brickkv::sha256_file_tree(fixture_root / "tree"),
                "artifact digest did not frame the root kind");
        std::filesystem::remove_all(fixture_root);

        LineageGate empty_text;
        const auto empty_request = empty_text.begin(
            request("", {{"system", ""}, {"user", ""}}), 1);
        require(empty_request.status == "cold",
                "empty scalar text diverged from the GenieX protocol");
        empty_text.abort(empty_request.transaction);

        LineageGate gate;
        std::vector<Message> initial{{"system", "policy"}, {"user", "first"}};
        const auto cold = gate.begin(request("", initial), 1);
        require(!cold.reuse && cold.status == "cold" &&
                    cold.reason == "first_request",
                "first request was not cold");
        const auto first = gate.commit(cold.transaction, "answer");
        initial.push_back({"assistant", "answer"});
        auto extension = initial;
        extension.push_back({"user", "second"});
        const auto hit = gate.begin(request(first.revision, extension), 1);
        require(hit.reuse && hit.reason == "exact_extension",
                "exact extension did not reuse");
        gate.abort(hit.transaction);

        LineageGate reloaded;
        const auto reload_cold = reloaded.begin(request("", initial), 7);
        const auto reload_parent =
            reloaded.commit(reload_cold.transaction, "answer");
        auto reload_extension = initial;
        reload_extension.push_back({"assistant", "answer"});
        reload_extension.push_back({"user", "next"});
        const auto planned_hit = reloaded.begin(
            request(reload_parent.revision, reload_extension), 7);
        const auto downgraded =
            reloaded.bind_generation(planned_hit.transaction, 8);
        require(!downgraded.reuse && downgraded.reason == "parent_mismatch",
                "model reload did not downgrade a planned hit");
        reloaded.abort(downgraded.transaction);

        const auto after_abort = gate.begin(request(first.revision, extension), 1);
        require(!after_abort.reuse && after_abort.reason == "parent_mismatch",
                "abort retained a reusable parent");
        gate.abort(after_abort.transaction);

        const auto fresh = gate.begin(request("", initial), 2);
        const auto second = gate.commit(fresh.transaction, "again");
        auto edited = initial;
        edited[1].content = "edited";
        edited.push_back({"user", "next"});
        const auto branch = gate.begin(request(second.revision, edited), 2);
        require(!branch.reuse && branch.reason == "branch",
                "edited prefix produced a cache hit");
        gate.abort(branch.transaction);

        LineageGate sessions;
        const auto base = sessions.begin(request("", initial), 3);
        const auto base_metadata = sessions.commit(base.transaction, "answer");
        auto switched_request = request(base_metadata.revision, extension);
        switched_request.session = kSessionB;
        const auto switched = sessions.begin(switched_request, 3);
        require(!switched.reuse && switched.reason == "session_switch",
                "session switch produced a cache hit");

        std::cout << "brickkv_lineage_test: passed\n";
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "brickkv_lineage_test: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
