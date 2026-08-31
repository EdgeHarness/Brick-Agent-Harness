cmake_minimum_required(VERSION 3.20)
project(brickkv_replay LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(BRICKKV_BUILD_REPLAY "Build the GenieX-backed replay executable" ON)
option(BRICKKV_SANITIZE "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
set(BRICKKV_GENIEX_ROOT "" CACHE PATH "Installed GenieX SDK root")

add_library(brickkv_lineage STATIC
    src/lineage.cpp
    src/sha256.cpp
)
target_include_directories(brickkv_lineage PUBLIC include)
if(MSVC)
    target_compile_options(brickkv_lineage PRIVATE /W4 /permissive- /utf-8)
else()
    target_compile_options(brickkv_lineage PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(BRICKKV_SANITIZE)
    if(MSVC)
        target_compile_options(brickkv_lineage PUBLIC /fsanitize=address)
        target_link_options(brickkv_lineage INTERFACE /fsanitize=address)
    else()
        target_compile_options(brickkv_lineage PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(brickkv_lineage INTERFACE -fsanitize=address,undefined)
    endif()
endif()

include(CTest)
if(BUILD_TESTING)
    add_executable(brickkv_lineage_test tests/lineage_test.cpp)
    target_link_libraries(brickkv_lineage_test PRIVATE brickkv_lineage)
    add_test(NAME brickkv_lineage_test COMMAND brickkv_lineage_test)
endif()

if(BRICKKV_BUILD_REPLAY)
    find_path(GENIEX_INCLUDE_DIR geniex.h
        HINTS "${BRICKKV_GENIEX_ROOT}/include"
        REQUIRED)
    find_library(GENIEX_LIBRARY NAMES geniex libgeniex
        HINTS "${BRICKKV_GENIEX_ROOT}/lib"
        REQUIRED)
    add_executable(brickkv-replay src/main.cpp)
    target_include_directories(brickkv-replay PRIVATE "${GENIEX_INCLUDE_DIR}")
    target_link_libraries(brickkv-replay PRIVATE brickkv_lineage "${GENIEX_LIBRARY}")
    if(WIN32)
        target_link_libraries(brickkv-replay PRIVATE Psapi Advapi32)
    endif()
    if(MSVC)
        target_compile_options(brickkv-replay PRIVATE /W4 /permissive- /utf-8)
    else()
        target_compile_options(brickkv-replay PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endif()
