# Host tests for the portable core (no hardware). Run: make -C tests
CC ?= gcc
CFLAGS = -std=c11 -O2 -Wall -Wextra -Wdouble-promotion -I../src/core -fsanitize=address,undefined -g
SRC = test_core.c ../src/core/channels.c ../src/core/curve.c ../src/core/fade.c ../src/core/frame.c \
      ../src/core/ledmodel.c ../src/core/params.c

test: test_core
	./test_core

test_core: $(SRC) $(wildcard ../src/core/*.h)
	$(CC) $(CFLAGS) -o $@ $(SRC) -lm

clean:
	rm -f test_core
.PHONY: test clean
