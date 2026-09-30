# Host tests for Board B's link client and group sync, plus a check that the protocol files
# copied from Board A haven't drifted.  make -C tests
C := ../components/xtm_driver
A := ../../board-a/src/core
CXXFLAGS := -std=gnu++20 -O1 -g -Wall -Wextra -fsanitize=address,undefined -fno-omit-frame-pointer -I$(C)
CFLAGS := -std=gnu17 -O1 -g -Wall -Wextra -fsanitize=address,undefined -fno-omit-frame-pointer -I$(C)

all: same run

same:
	@cmp $(C)/link_protocol.h $(A)/link_protocol.h
	@cmp $(C)/frame.h $(A)/frame.h
	@cmp $(C)/frame_c.h $(A)/frame.c
	@echo "protocol files match Board A"

test_board_b: test_board_b.cpp $(C)/link_client.cpp $(C)/sync_core.cpp $(C)/xtm_wire.c $(C)/*.h
	$(CC) $(CFLAGS) -c $(C)/xtm_wire.c -o xtm_wire.o
	$(CXX) $(CXXFLAGS) test_board_b.cpp $(C)/link_client.cpp $(C)/sync_core.cpp xtm_wire.o -o $@

run: test_board_b
	./test_board_b

clean:
	rm -f test_board_b xtm_wire.o

.PHONY: all same run clean
