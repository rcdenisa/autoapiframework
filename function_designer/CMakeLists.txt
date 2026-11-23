# *******************************************************************************
# Copyright (c) 2026 ZF Friedrichshafen AG
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# 
# Contributors:
#   Thomas Pfleiderer - initial function designer
# *******************************************************************************

cmake_minimum_required(VERSION 3.16)

project(function_designer
        VERSION 0.1.0
        DESCRIPTION "Editor for Eclipse autoapiframework function specifications"
        LANGUAGES CXX)

include(CTest)
option(AFD_BUILD_APP "Build the wxWidgets function designer application" ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_RUNTIME_OUTPUT_DIRECTORY)
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
endif()


find_program(VSPEC_EXECUTABLE
    NAMES vspec vspec.exe
    HINTS
        "$ENV{HOME}/venvs/vss-tools/bin"
        "$ENV{USERPROFILE}/venvs/vss-tools/Scripts"
)

if(NOT VSPEC_EXECUTABLE)
    message(WARNING
        "vss-tools not installed - importing signals from vspec files will be disabled at runtime.")
    set(VSPEC_EXECUTABLE "")
endif()

# ---------------------------------------------------------------------------
# Python tooling (validate_afs.py / generate_adapter.py)
# ---------------------------------------------------------------------------
find_program(AFD_PYTHON_EXECUTABLE
    NAMES python python3 python.exe python3.exe
    HINTS
        "$ENV{VIRTUAL_ENV}/bin"
        "$ENV{VIRTUAL_ENV}/Scripts"
        "$ENV{USERPROFILE}/venvs/vss-tools/Scripts"
        "$ENV{HOME}/venvs/vss-tools/bin"
)

if(NOT AFD_PYTHON_EXECUTABLE)
    message(WARNING
        "Python not found - validate_afs.py and generate_adapter.py will be disabled at runtime.")
    set(AFD_PYTHON_EXECUTABLE "")
endif()

set(AFD_TOOLS_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/tools")


option(ACD_FETCH_WXWIDGETS "Download and build wxWidgets when no installation is found" ON)

# vcpkg and recent wxWidgets installations provide a package config file,
# system installations are found through CMake's FindwxWidgets module.
find_package(wxWidgets CONFIG QUIET COMPONENTS core base adv)
if(NOT wxWidgets_FOUND)
    find_package(wxWidgets QUIET COMPONENTS core base adv)
endif()

if(wxWidgets_FOUND)
    if(wxWidgets_USE_FILE)
        include(${wxWidgets_USE_FILE})
    endif()
    set(ACD_WX_LIBRARIES ${wxWidgets_LIBRARIES})
elseif(ACD_FETCH_WXWIDGETS)
    message(STATUS "wxWidgets not found - building it from source (this takes a while on the first run)")
    include(FetchContent)
    # wxWidgets 3.2.x declares a CMake minimum below 3.5, which CMake 4+ rejects.
    if(NOT DEFINED CMAKE_POLICY_VERSION_MINIMUM)
        set(CMAKE_POLICY_VERSION_MINIMUM 3.5)
    endif()
    set(wxBUILD_SHARED OFF CACHE BOOL "" FORCE)
    set(wxBUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(wxBUILD_SAMPLES OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(wxWidgets
        GIT_REPOSITORY https://github.com/wxWidgets/wxWidgets.git
        GIT_TAG v3.2.6
            GIT_SHALLOW TRUE
            SYSTEM)
    # wxWidgets itself must never be built with warnings as errors.
    set(CMAKE_COMPILE_WARNING_AS_ERROR OFF)
    FetchContent_MakeAvailable(wxWidgets)
    if(CMAKE_VERSION VERSION_LESS 3.24)
        foreach(wx_target wxbase wxcore wxadv)
            if(TARGET ${wx_target})
                target_compile_options(${wx_target} PRIVATE /WX-)
            endif()
        endforeach()
    endif()
    set(ACD_WX_LIBRARIES wx::core wx::base)
else()
    message(FATAL_ERROR
        "wxWidgets not found. Install it (vcpkg: 'vcpkg install wxwidgets', "
        "Linux: 'libwxgtk3.2-dev') or configure with -DACD_FETCH_WXWIDGETS=ON.")
endif()

if(WIN32)
    enable_language(RC)
    configure_file(src/app_icon.rc.in app_icon.rc @ONLY)
    set(ACD_WINDOWS_RESOURCES "${CMAKE_CURRENT_BINARY_DIR}/app_icon.rc")
endif()

    # GUI executable for the Auto API Function Designer application
    add_executable(AutoAPIFunctionDesigner WIN32
        src/main.cpp
        src/main_frame.cpp
        src/json_signal_parser.cpp
        src/yaml_node.cpp
        src/yaml_parser.cpp
        src/yaml_writer.cpp
        src/meta_model.cpp
        src/validate_function.cpp    
        src/function_specification.cpp
        src/supervision_editor.cpp
        ${ACD_WINDOWS_RESOURCES}
    )

target_include_directories(AutoAPIFunctionDesigner PRIVATE src)
target_link_libraries(AutoAPIFunctionDesigner PRIVATE ${ACD_WX_LIBRARIES})
target_compile_definitions(AutoAPIFunctionDesigner PRIVATE
    AFD_VSPEC_EXECUTABLE="${VSPEC_EXECUTABLE}"
    AFD_PYTHON_EXECUTABLE="${AFD_PYTHON_EXECUTABLE}"
    AFD_TOOLS_DIR="$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools")

    if(MSVC)
        # /external:W0 silences warnings from wx headers (SYSTEM include dirs) while /WX stays active for our code.
        target_compile_options(AutoAPIFunctionDesigner PRIVATE /W4 /WX /utf-8 /external:W0)
        target_compile_definitions(AutoAPIFunctionDesigner PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN _CRT_SECURE_NO_WARNINGS)
        # CMake < 3.25 ignores SYSTEM for FetchContent, so mark the wx include dirs external manually.
        if(TARGET wxbase)
            get_target_property(ACD_WX_INCLUDES wxbase INTERFACE_INCLUDE_DIRECTORIES)
            foreach(ACD_WX_INC IN LISTS ACD_WX_INCLUDES)
                if(NOT ACD_WX_INC MATCHES "^\\$<")
                    target_compile_options(AutoAPIFunctionDesigner PRIVATE "/external:I${ACD_WX_INC}")
                endif()
            endforeach()
        endif()
        set_property(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PROPERTY VS_STARTUP_PROJECT AutoAPIFunctionDesigner)
    else()
        target_compile_options(AutoAPIFunctionDesigner PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()

set_target_properties(AutoAPIFunctionDesigner PROPERTIES
    VS_DEBUGGER_WORKING_DIRECTORY "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>")

if(UNIX AND NOT APPLE)
    set(ACD_LINUX_ICON_COMMAND
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${CMAKE_CURRENT_SOURCE_DIR}/autoapiframework_icon-128x128.png"
                "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/autoapiframework_icon.png")
endif()

# The meta model and the sample specification are picked up next to the executable.
add_custom_command(TARGET AutoAPIFunctionDesigner POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/examples/autoapiframework_metadata_V04.yaml"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/autoapiframework_meta_model.yaml"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/examples/speed_hazard_detection.afs"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/speed_hazard_detection.afs"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/examples/vehicle_speed_fusion_multirate.afs"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/vehicle_speed_fusion_multirate.afs"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${CMAKE_CURRENT_SOURCE_DIR}/examples/mandatory_property_is_missing_syntax_error.afs"            
                "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/mandatory_property_is_missing_syntax_error.afs"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/examples/wheel_speed_plausibility_check.afs"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/wheel_speed_plausibility_check.afs"            
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/autoapiframework_logo.png"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/autoapiframework_logo.png"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/autoapiframework_logo_large.png"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/autoapiframework_logo_large.png"
    ${ACD_LINUX_ICON_COMMAND}
    VERBATIM)

# Copy the Python tooling directory next to the executable so the GUI can call it.
# DEPENDS lists the individual source files so CMake re-runs this command
# automatically whenever any of them changes � no manual rebuild needed.
add_custom_command(TARGET AutoAPIFunctionDesigner POST_BUILD
    DEPENDS
        "${AFD_TOOLS_SOURCE_DIR}/afs_model.py"
        "${AFD_TOOLS_SOURCE_DIR}/afs_common.py"
        "${AFD_TOOLS_SOURCE_DIR}/validate_afs.py"
        "${AFD_TOOLS_SOURCE_DIR}/generate_adapter.py"
        "${AFD_TOOLS_SOURCE_DIR}/requirements.txt"
        "${AFD_TOOLS_SOURCE_DIR}/templates/api.hpp.jinja2"
        "${AFD_TOOLS_SOURCE_DIR}/templates/api_c.h.jinja2"
        "${AFD_TOOLS_SOURCE_DIR}/templates/api.rs.jinja2"
        "${AFD_TOOLS_SOURCE_DIR}/templates/autoapiframework_enums.hpp.jinja2"
        "${AFD_TOOLS_SOURCE_DIR}/templates/autoapiframework_enums_c.h.jinja2"
        "${AFD_TOOLS_SOURCE_DIR}/templates/autoapiframework_enums.rs.jinja2"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/afs_model.py"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/afs_model.py"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/afs_common.py"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/afs_common.py"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/validate_afs.py"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/validate_afs.py"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/generate_adapter.py"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/generate_adapter.py"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/requirements.txt"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/requirements.txt"
    COMMAND ${CMAKE_COMMAND} -E make_directory
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/templates"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/templates/api.hpp.jinja2"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/templates/api.hpp.jinja2"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/templates/api_c.h.jinja2"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/templates/api_c.h.jinja2"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/templates/api.rs.jinja2"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/templates/api.rs.jinja2"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/templates/autoapiframework_enums.hpp.jinja2"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/templates/autoapiframework_enums.hpp.jinja2"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/templates/autoapiframework_enums_c.h.jinja2"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/templates/autoapiframework_enums_c.h.jinja2"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${AFD_TOOLS_SOURCE_DIR}/templates/autoapiframework_enums.rs.jinja2"
            "$<TARGET_FILE_DIR:AutoAPIFunctionDesigner>/tools/templates/autoapiframework_enums.rs.jinja2"
    COMMENT "Copying Python tools/ next to executable"
    VERBATIM)

install(TARGETS AutoAPIFunctionDesigner RUNTIME DESTINATION bin)
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/examples/autoapiframework_meta_model.yaml" DESTINATION bin)
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/autoapiframework_logo.png" DESTINATION bin)
if(UNIX AND NOT APPLE)
    install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/autoapiframework_icon-128x128.png"
            DESTINATION bin
            RENAME autoapiframework_icon.png)
endif()

    # Commandline executable for the Auto API Function Designer syntax check tool
    add_executable(AutoAPIFunctionDesigner_SyntaxCheck
        src/syntax_check/main.cpp
        src/yaml_node.cpp
        src/yaml_parser.cpp
        src/meta_model.cpp
        src/validate_function.cpp
    )

    target_include_directories(AutoAPIFunctionDesigner_SyntaxCheck PRIVATE src)
    target_compile_definitions(AutoAPIFunctionDesigner_SyntaxCheck PRIVATE
        AFD_EXAMPLES_DIR="${CMAKE_CURRENT_SOURCE_DIR}/examples")
    if(MSVC)
        target_compile_options(AutoAPIFunctionDesigner_SyntaxCheck PRIVATE /W4 /WX /utf-8)
    else()
        target_compile_options(AutoAPIFunctionDesigner_SyntaxCheck PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()

# Standalone AFS parser CLI; it does not depend on the wxWidgets application.
add_executable(AfsFileParser
    src/afs_file_parser/main.cpp
    src/afs_file_parser/afs_file_expectation.cpp
    src/afs_file_parser/afs_file_parser.cpp
    src/yaml_node.cpp
    src/yaml_parser.cpp
)
target_include_directories(AfsFileParser PRIVATE src/afs_file_parser)
if(MSVC)
    target_compile_options(AfsFileParser PRIVATE /W4 /WX /utf-8)
else()
    target_compile_options(AfsFileParser PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
install(TARGETS AfsFileParser RUNTIME DESTINATION bin)

# ---------------------------------------------------------------------------
# Command-line tools written in Python and frozen with PyInstaller. They are
# built with the normal build, into the same bin/ directory as
# AutoAPIFunctionDesigner_SyntaxCheck and AfsFileParser:
#   AutoAPIFunctionDesigner_ValidateAFS <file.afs>      full validation
#   AutoAPIFunctionDesigner_CodeGen_1   <file.afs> ...  API/skeleton generation
# ---------------------------------------------------------------------------
option(AFD_BUILD_PYTHON_TOOLS "Build the stand-alone ValidateAFS and CodeGen_1 executables (needs Python 3.9-3.14 and internet on first build)" ON)
set(AFD_TOOL_PYTHON "" CACHE FILEPATH "Python 3.9-3.14 used to build the Python tools (auto-detected when empty)")

function(afd_find_tool_python result)
    set(candidates "")
    if(AFD_TOOL_PYTHON)
        list(APPEND candidates "${AFD_TOOL_PYTHON}")
    endif()
    if(WIN32)
        # The py launcher knows every installed interpreter.
        foreach(version 3.13 3.12 3.11 3.10 3.14 3.9)
            execute_process(COMMAND py -${version} -c "import sys;print(sys.executable)"
                            OUTPUT_VARIABLE found RESULT_VARIABLE rc
                            OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
            if(rc EQUAL 0 AND found)
                list(APPEND candidates "${found}")
            endif()
        endforeach()
    endif()
    if(AFD_PYTHON_EXECUTABLE)
        list(APPEND candidates "${AFD_PYTHON_EXECUTABLE}")
    endif()
    foreach(name python3 python)
        find_program(afd_candidate_${name} NAMES ${name})
        if(afd_candidate_${name})
            list(APPEND candidates "${afd_candidate_${name}}")
        endif()
    endforeach()

    foreach(candidate IN LISTS candidates)
        # Needs a supported version plus venv/ensurepip (missing in e.g. MSYS2 Python).
        execute_process(COMMAND "${candidate}" -c
                "import sys, venv, ensurepip; sys.exit(0 if (3, 9) <= sys.version_info[:2] < (3, 15) else 1)"
                RESULT_VARIABLE rc OUTPUT_QUIET ERROR_QUIET)
        if(rc EQUAL 0)
            set(${result} "${candidate}" PARENT_SCOPE)
            return()
        endif()
    endforeach()
    set(${result} "" PARENT_SCOPE)
endfunction()

if(AFD_BUILD_PYTHON_TOOLS)
    afd_find_tool_python(AFD_TOOL_PYTHON_FOUND)
    if(AFD_TOOL_PYTHON_FOUND)
        message(STATUS "Python tools (ValidateAFS, CodeGen_1): building with ${AFD_TOOL_PYTHON_FOUND}")
        file(GLOB AFD_TEMPLATE_FILES CONFIGURE_DEPENDS "${AFD_TOOLS_SOURCE_DIR}/templates/*.jinja2")

        # afd_add_python_exe(<target> <script>) freezes tools/<script> into bin/<target>(.exe)
        function(afd_add_python_exe target script)
            set(exe "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/${target}${CMAKE_EXECUTABLE_SUFFIX}")
            add_custom_command(
                OUTPUT "${exe}"
                COMMAND "${AFD_TOOL_PYTHON_FOUND}" "${AFD_TOOLS_SOURCE_DIR}/build_exe.py"
                        --script "${script}" --name "${target}"
                        --output-dir "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}"
                        --work-dir "${CMAKE_BINARY_DIR}/python_tools_build"
                DEPENDS
                    "${AFD_TOOLS_SOURCE_DIR}/build_exe.py"
                    "${AFD_TOOLS_SOURCE_DIR}/afs_common.py"
                    "${AFD_TOOLS_SOURCE_DIR}/afs_model.py"
                    "${AFD_TOOLS_SOURCE_DIR}/validate_afs.py"
                    "${AFD_TOOLS_SOURCE_DIR}/generate_adapter.py"
                    "${AFD_TOOLS_SOURCE_DIR}/requirements.txt"
                    "${AFD_TOOLS_SOURCE_DIR}/requirements-build.txt"
                    ${AFD_TEMPLATE_FILES}
                COMMENT "Building ${target} (PyInstaller)"
                VERBATIM)
            add_custom_target(${target} ALL DEPENDS "${exe}")
            install(PROGRAMS "${exe}" DESTINATION bin)
            set(${target}_EXE "${exe}" PARENT_SCOPE)
        endfunction()

        afd_add_python_exe(AutoAPIFunctionDesigner_ValidateAFS validate_afs.py)
        afd_add_python_exe(AutoAPIFunctionDesigner_CodeGen_1 generate_adapter.py)
        # Both share one virtual environment: never build them in parallel.
        add_dependencies(AutoAPIFunctionDesigner_CodeGen_1 AutoAPIFunctionDesigner_ValidateAFS)
    else()
        message(WARNING
            "ValidateAFS and CodeGen_1 are not built: no Python 3.9-3.14 with venv found. "
            "Install one or pass -DAFD_TOOL_PYTHON=<path to python>.")
    endif()
endif()

if(BUILD_TESTING)
    add_executable(afs_file_parser_tests
        tests/afs_file_parser_tests.cpp
        src/afs_file_parser/afs_file_parser.cpp
        src/yaml_node.cpp
        src/yaml_parser.cpp
    )
    target_include_directories(afs_file_parser_tests PRIVATE src/afs_file_parser)
    target_compile_definitions(afs_file_parser_tests PRIVATE
        AFS_PARSER_EXAMPLES_DIR="${CMAKE_CURRENT_SOURCE_DIR}/examples")
    if(MSVC)
        target_compile_options(afs_file_parser_tests PRIVATE /W4 /WX /utf-8)
    else()
        target_compile_options(afs_file_parser_tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()
    add_test(NAME afs_file_parser_tests COMMAND afs_file_parser_tests)

    add_executable(function_designer_tests
        tests/function_designer_tests.cpp
        src/function_specification.cpp
        src/yaml_node.cpp
        src/yaml_parser.cpp
        src/yaml_writer.cpp
    )
    target_include_directories(function_designer_tests PRIVATE src)
    target_compile_definitions(function_designer_tests PRIVATE
        AFD_EXAMPLES_DIR="${CMAKE_CURRENT_SOURCE_DIR}/examples"
        AFD_TESTS_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests")
    if(MSVC)
        target_compile_options(function_designer_tests PRIVATE /W4 /WX /utf-8)
    else()
        target_compile_options(function_designer_tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()
    add_test(NAME function_designer_tests COMMAND function_designer_tests)

    add_executable(yaml_comment_tests
        tests/yaml_comment_tests.cpp
        src/yaml_node.cpp
        src/yaml_parser.cpp
        src/yaml_writer.cpp
    )
    target_include_directories(yaml_comment_tests PRIVATE src)
    if(MSVC)
        target_compile_options(yaml_comment_tests PRIVATE /W4 /WX /utf-8)
    else()
        target_compile_options(yaml_comment_tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()
    add_test(NAME yaml_comment_tests COMMAND yaml_comment_tests)

    # Unit tests for ValidateFunction / MetaModel — no wxWidgets dependency.
    add_executable(syntax_check_tests
        tests/syntax_check_tests.cpp
        src/yaml_node.cpp
        src/yaml_parser.cpp
        src/meta_model.cpp
        src/validate_function.cpp
    )
    target_include_directories(syntax_check_tests PRIVATE src)
    target_compile_definitions(syntax_check_tests PRIVATE
        AFD_EXAMPLES_DIR="${CMAKE_CURRENT_SOURCE_DIR}/examples")
    if(MSVC)
        target_compile_options(syntax_check_tests PRIVATE /W4 /WX /utf-8)
    else()
        target_compile_options(syntax_check_tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()
    add_test(NAME syntax_check_tests COMMAND syntax_check_tests)

    # Integration tests that invoke the CLI executable as a subprocess.
    # Each test uses PASS_REGULAR_EXPRESSION so the expected output is verified
    # regardless of whether the exit code is zero or non-zero.
    if(AFD_BUILD_APP)
        set(SC_EXE "$<TARGET_FILE:AutoAPIFunctionDesigner_SyntaxCheck>")
        set(EX_DIR "${CMAKE_CURRENT_SOURCE_DIR}/examples")

        add_test(NAME syntax_check_cli_speed_hazard
                 COMMAND "${SC_EXE}" "${EX_DIR}/speed_hazard_detection.afs")
        set_tests_properties(syntax_check_cli_speed_hazard PROPERTIES
                             PASS_REGULAR_EXPRESSION "Syntax OK")

        add_test(NAME syntax_check_cli_vehicle_speed_fusion
                 COMMAND "${SC_EXE}" "${EX_DIR}/vehicle_speed_fusion_multirate.afs")
        set_tests_properties(syntax_check_cli_vehicle_speed_fusion PROPERTIES
                             PASS_REGULAR_EXPRESSION "Syntax OK")

        add_test(NAME syntax_check_cli_wheel_speed
                 COMMAND "${SC_EXE}" "${EX_DIR}/wheel_speed_plausibility_check.afs")
        set_tests_properties(syntax_check_cli_wheel_speed PROPERTIES
                             PASS_REGULAR_EXPRESSION "Syntax OK")

        add_test(NAME syntax_check_cli_mandatory_missing
                 COMMAND "${SC_EXE}"
                         "${EX_DIR}/mandatory_property_is_missing_syntax_error.afs")
        set_tests_properties(syntax_check_cli_mandatory_missing PROPERTIES
                             PASS_REGULAR_EXPRESSION "Syntax error")

        add_test(NAME syntax_check_cli_missing_file
                 COMMAND "${SC_EXE}" "nonexistent_file.afs")
        set_tests_properties(syntax_check_cli_missing_file PROPERTIES
                             PASS_REGULAR_EXPRESSION "Could not read")

        add_test(NAME syntax_check_cli_no_args COMMAND "${SC_EXE}")
        set_tests_properties(syntax_check_cli_no_args PROPERTIES
                             PASS_REGULAR_EXPRESSION "Usage:")
    endif() #(AFD_BUILD_APP)

    # CLI tests for the Python tools, same style as the syntax check tests.
    if(TARGET AutoAPIFunctionDesigner_ValidateAFS)
        set(VA_EXE "${AutoAPIFunctionDesigner_ValidateAFS_EXE}")
        set(CG_EXE "${AutoAPIFunctionDesigner_CodeGen_1_EXE}")
        set(AT_EX_DIR "${CMAKE_CURRENT_SOURCE_DIR}/examples")

        add_test(NAME validate_afs_cli_speed_hazard
                 COMMAND "${VA_EXE}" "${AT_EX_DIR}/speed_hazard_detection.afs")
        set_tests_properties(validate_afs_cli_speed_hazard PROPERTIES
                             PASS_REGULAR_EXPRESSION "passed validation")

        add_test(NAME validate_afs_cli_mandatory_missing
                 COMMAND "${VA_EXE}" "${AT_EX_DIR}/mandatory_property_is_missing_syntax_error.afs")
        set_tests_properties(validate_afs_cli_mandatory_missing PROPERTIES
                             PASS_REGULAR_EXPRESSION "FAILED")

        add_test(NAME validate_afs_cli_missing_file COMMAND "${VA_EXE}" "nonexistent_file.afs")
        set_tests_properties(validate_afs_cli_missing_file PROPERTIES
                             PASS_REGULAR_EXPRESSION "File not found")

        add_test(NAME validate_afs_cli_help COMMAND "${VA_EXE}" --help)
        set_tests_properties(validate_afs_cli_help PROPERTIES
                             PASS_REGULAR_EXPRESSION "usage: AutoAPIFunctionDesigner_ValidateAFS")

        add_test(NAME codegen_1_clean
                 COMMAND ${CMAKE_COMMAND} -E remove_directory "${CMAKE_BINARY_DIR}/codegen_1_test_out")
        set_tests_properties(codegen_1_clean PROPERTIES FIXTURES_SETUP codegen_1_clean)

        add_test(NAME codegen_1_cli_cpp
                 COMMAND "${CG_EXE}" "${AT_EX_DIR}/speed_hazard_detection.afs"
                         --language cpp --output-dir "${CMAKE_BINARY_DIR}/codegen_1_test_out")
        set_tests_properties(codegen_1_cli_cpp PROPERTIES
                             FIXTURES_REQUIRED codegen_1_clean
                             FIXTURES_SETUP codegen_1_generated
                             PASS_REGULAR_EXPRESSION "Generated: .*speed_hazard_detection[/\\\\]api[/\\\\]speed_hazard_detection_api\\.h")

        # The generated tree must have the agreed layout: only the api header and the shared enums.
        add_test(NAME codegen_1_layout
                 COMMAND ${CMAKE_COMMAND}
                         -DROOT=${CMAKE_BINARY_DIR}/codegen_1_test_out
                         -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/check_codegen_1_layout.cmake")
        set_tests_properties(codegen_1_layout PROPERTIES FIXTURES_REQUIRED codegen_1_generated)

        # api.h + enums must compile together (checked with the C++ compiler used for this build).
        if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
            add_test(NAME codegen_1_api_compiles
                     COMMAND "${CMAKE_CXX_COMPILER}" -std=c++17 -Wall -Wextra -Wpedantic -Werror
                             -Wno-pragma-once-outside-header -fsyntax-only -x c++
                             "${CMAKE_BINARY_DIR}/codegen_1_test_out/cpp/speed_hazard_detection/api/speed_hazard_detection_api.h")
            set_tests_properties(codegen_1_api_compiles PROPERTIES FIXTURES_REQUIRED codegen_1_generated)
        endif()

        add_test(NAME codegen_1_cli_invalid_afs
                 COMMAND "${CG_EXE}" "${AT_EX_DIR}/mandatory_property_is_missing_syntax_error.afs"
                         --output-dir "${CMAKE_BINARY_DIR}/codegen_1_test_out")
        set_tests_properties(codegen_1_cli_invalid_afs PROPERTIES
                             PASS_REGULAR_EXPRESSION "Generation aborted")

        add_test(NAME codegen_1_cli_help COMMAND "${CG_EXE}" --help)
        set_tests_properties(codegen_1_cli_help PROPERTIES
                             PASS_REGULAR_EXPRESSION "usage: AutoAPIFunctionDesigner_CodeGen_1")
    endif() #(TARGET AutoAPIFunctionDesigner_ValidateAFS)
endif() #(BUILD_TESTING)
