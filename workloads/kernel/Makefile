CC ?= gcc
CFLAGS ?= -O3 -Wall -Wextra -pthread
TARGET = fixed_compute

all: $(TARGET)

$(TARGET): fixed_compute.c
	$(CC) $(CFLAGS) -o $(TARGET) fixed_compute.c

clean:
	rm -f $(TARGET) $(TARGET).exe *.o

.PHONY: all clean
