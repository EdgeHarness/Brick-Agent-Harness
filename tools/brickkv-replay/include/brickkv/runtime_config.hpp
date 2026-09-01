#pragma once

#include <string_view>

namespace brickkv {

// QAIRT model bundles own their context configuration. GenieX documents zero
// as "from model" and the QAIRT plugin rejects any non-zero n_ctx override.
constexpr int runtime_n_ctx(const std::string_view plugin,
                            const int requested_context) noexcept {
    return plugin == "qairt" ? 0 : requested_context;
}

}  // namespace brickkv
