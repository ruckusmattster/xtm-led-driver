# Toolchain file for arm-none-eabi-gcc (Arm GNU Toolchain or xPack build).
# Put the toolchain's bin directory on PATH, or pass -DARM_TOOLCHAIN_DIR=/path/to/bin.
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

if(DEFINED ARM_TOOLCHAIN_DIR)
  set(_p "${ARM_TOOLCHAIN_DIR}/")
else()
  set(_p "")
endif()
set(CMAKE_C_COMPILER   ${_p}arm-none-eabi-gcc)
set(CMAKE_ASM_COMPILER ${_p}arm-none-eabi-gcc)
set(CMAKE_OBJCOPY      ${_p}arm-none-eabi-objcopy CACHE FILEPATH "")
set(CMAKE_SIZE         ${_p}arm-none-eabi-size CACHE FILEPATH "")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
