# Board A firmware (STM32G431CBU6).
#   cmake -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake
#   cmake --build build
# Produces build/board_a.elf, .bin and .hex.
cmake_minimum_required(VERSION 3.20)
if(NOT CMAKE_TOOLCHAIN_FILE)
  set(CMAKE_TOOLCHAIN_FILE ${CMAKE_CURRENT_SOURCE_DIR}/cmake/arm-none-eabi.cmake)
endif()
project(xtm_board_a C ASM)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

set(TP ${CMAKE_CURRENT_SOURCE_DIR}/third_party)
set(SOURCES
  src/main.c src/syscalls.c
  src/app/control.c src/app/console.c src/app/link.c src/app/settings.c
  src/core/channels.c src/core/curve.c src/core/fade.c src/core/frame.c src/core/ledmodel.c src/core/params.c
  src/hw/hw_core.c src/hw/hw_adc.c src/hw/hw_analog.c src/hw/hw_dac80504.c src/hw/hw_uart.c src/hw/hw_flash.c
  ${TP}/cmsis_device_g4/Source/system_stm32g4xx.c
  ${TP}/cmsis_device_g4/Source/startup_stm32g431xx.s)

add_executable(board_a.elf ${SOURCES})
target_include_directories(board_a.elf PRIVATE
  src src/app src/core src/hw
  ${TP}/cmsis/Include ${TP}/cmsis_device_g4/Include ${TP}/stm32g4xx_ll/Inc)
target_compile_definitions(board_a.elf PRIVATE STM32G431xx)
set(CPU -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard)
target_compile_options(board_a.elf PRIVATE ${CPU}
  $<$<COMPILE_LANGUAGE:C>:-std=gnu11 -Wall -Wextra -Wdouble-promotion -Wno-unused-parameter -fno-common
  -ffunction-sections -fdata-sections -O2 -g3>
  $<$<COMPILE_LANGUAGE:ASM>:-x assembler-with-cpp>)
target_link_options(board_a.elf PRIVATE ${CPU}
  -T${CMAKE_CURRENT_SOURCE_DIR}/linker/stm32g431cbux.ld
  -specs=nano.specs -specs=nosys.specs -u _printf_float
  -Wl,--gc-sections -Wl,--no-warn-rwx-segments -Wl,-Map=${CMAKE_BINARY_DIR}/board_a.map -Wl,--print-memory-usage)
target_link_libraries(board_a.elf PRIVATE m)

add_custom_command(TARGET board_a.elf POST_BUILD
  COMMAND ${CMAKE_OBJCOPY} -O binary board_a.elf board_a.bin
  COMMAND ${CMAKE_OBJCOPY} -O ihex board_a.elf board_a.hex
  COMMAND ${CMAKE_SIZE} board_a.elf
  WORKING_DIRECTORY ${CMAKE_BINARY_DIR})
