################################################################################
#
# Makefile for waveform demo
#
################################################################################

# Set the default target for just 'make' to all
.DEFAULT_GOAL := all

SOURCE_DIR:=src

BUILD_DIR:=build

ELEMENT_NAME:=waveform

# C sources
C_SRCS := \
    $(wildcard $(SOURCE_DIR)/*.c)

# C++ Sources
CC_SRCS := \
    $(wildcard $(SOURCE_DIR)/*.cc)

C_OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(C_SRCS:.c=.o)))
vpath %.c $(sort $(dir $(C_SRCS)))
CC_OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(CC_SRCS:.cc=.o)))
vpath %.cc $(sort $(dir $(CC_SRCS)))

# Flags shared between C and C++
SHARED_FLAGS := \
           -Wall \
           -Werror \
           -Wsign-compare \
           -Wmaybe-uninitialized \
           -Iinc/

# Flags only used with C
CFLAGS := -Wconversion

# Flags used only with C++
CXXFLAGS := -std=c++11

# Linker flags
LDFLAGS := \
    -lpthread \
    -lrt \
    -lm \
    -latomcpp \
    -latom \
    -lhiredis \
    -lmsgpackc

#
# Element Build
#

$(BUILD_DIR)/%.o: %.c | $(BUILD_DIR)
	@ echo "Compiling $<"
	@ $(CC) -c $(SHARED_FLAGS) $(CFLAGS) -o $@ $<

$(BUILD_DIR)/%.o : %.cc | $(BUILD_DIR)
	@ echo "Compiling $<"
	@ $(CXX) -c $(CXXFLAGS) $(SHARED_FLAGS) -o $@ $<

$(BUILD_DIR)/$(ELEMENT_NAME): $(C_OBJS) $(CC_OBJS) | $(BUILD_DIR)
	@ echo "Linking $@"
	@ $(CXX) $^ -o $@ $(LDFLAGS)

$(BUILD_DIR):
	@ echo "Creating $@"
	@ mkdir $@

.PHONY: all
all: $(BUILD_DIR)/$(ELEMENT_NAME)

.PHONY: clean
clean:
	rm -rf $(TEST_BUILD_DIR)
	rm -rf $(BUILD_DIR)
