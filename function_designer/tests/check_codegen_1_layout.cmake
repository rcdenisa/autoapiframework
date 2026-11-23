# Checks the layout written by Code Generator 1 (run with: cmake -DROOT=<dir> -P this file).
# Code Generator 1 creates only the api header and the shared enums file;
# adapter/ (Code Generator 2) and middleware/ (Code Generator 3) must not exist.

set(function_dir "${ROOT}/cpp/speed_hazard_detection")

foreach(expected
        "${ROOT}/cpp/common/autoapiframework_enums.h"
        "${function_dir}/api/speed_hazard_detection_api.h")
    if(NOT EXISTS "${expected}")
        message(FATAL_ERROR "missing generated file: ${expected}")
    endif()
endforeach()

foreach(unexpected "${function_dir}/adapter" "${function_dir}/middleware")
    if(EXISTS "${unexpected}")
        message(FATAL_ERROR "must not be created by Code Generator 1: ${unexpected}")
    endif()
endforeach()

file(GLOB_RECURSE all_files RELATIVE "${ROOT}" "${ROOT}/*")
list(LENGTH all_files file_count)
if(NOT file_count EQUAL 2)
    message(FATAL_ERROR "expected exactly 2 generated files, found ${file_count}: ${all_files}")
endif()
