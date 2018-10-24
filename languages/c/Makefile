################################################################################
#
# Makefile for libatom.so
#
################################################################################

# Set the default target for just 'make' to all
.DEFAULT_GOAL := all

OUTPUT_NAME := libatom.so

# Check the install prefix
ifeq ($(PREFIX),)
	PREFIX:=/usr/lib
endif

# Install directory name
INSTALL_DIR:=atom

SOURCE_DIR:=src
INCLUDE_DIR:=inc

BUILD_DIR:=build
THIRDPARTY_DIR:=third-party
HIREDIS_BUILD_DIR:=/usr/local

C_SRCS := $(wildcard $(SOURCE_DIR)/*.c)
C_OBJS = $(addprefix $(BUILD_DIR)/lib/,$(notdir $(C_SRCS:.c=.o)))
vpath %.c $(sort $(dir $(C_SRCS)))

HEADER_SRCS := $(wildcard $(INCLUDE_DIR)/*.h)
HEADER_OBJS = $(addprefix $(BUILD_DIR)/inc/,$(notdir $(HEADER_SRCS)))
vpath %.h $(sort $(dir $(HEADER_SRCS)))

TEST_DIR:=test
TEST_BINARY:=test_atom
TEST_SRCS := $(wildcard $(TEST_DIR)/*.cc)
TEST_OBJS = $(addprefix $(TEST_DIR)/$(BUILD_DIR)/,$(notdir $(TEST_SRCS:.cc=.o)))
vpath %.cc $(sort $(dir $(TEST_SRCS)))

# Check to see if we got a test filter
ifeq ($(TEST_FILTER),)
	TEST_FILTER:="*"
endif

# CFLAGS
CFLAGS := -Wall -Werror -fPIC -I${INCLUDE_DIR} -I${HIREDIS_BUILD_DIR}/include/ -g

#LDFLAGS
LDFLAGS := -L${HIREDIS_BUILD_DIR}/lib -Wl,-rpath,${HIREDIS_BUILD_DIR}/lib -lhiredis -lpthread

$(BUILD_DIR)/lib/%.o: src/%.c $(HEADER_OBJS) | $(BUILD_DIR)/lib
	@ echo "Compiling $<"
	@ $(CC) -c $(CFLAGS) -o $@ $(filter %.c,$^)

$(BUILD_DIR)/inc/%.h: %.h | $(BUILD_DIR)/inc
	@ echo "Copying $<"
	@ cp $< $@

$(BUILD_DIR)/lib/$(OUTPUT_NAME): $(C_OBJS) $(HEADER_OBJS) | $(BUILD_DIR)/lib
	@ echo "Linking $@"
	@ $(CC) -shared $(filter %.o,$^) ${LDFLAGS} -o $@

$(BUILD_DIR)/inc: | $(BUILD_DIR)
	@ echo "Creating $@"
	@ mkdir $@

$(BUILD_DIR)/lib: | $(BUILD_DIR)
	@ echo "Creating $@"
	@ mkdir $@

$(BUILD_DIR):
	@ echo "Creating $@"
	@ mkdir $@

$(TEST_DIR)/$(BUILD_DIR):
	@ echo "Creating $@"
	@ mkdir $@

$(TEST_DIR)/$(BUILD_DIR)/%.o: test/%.cc $(HEADER_OBJS) | $(TEST_DIR)/$(BUILD_DIR)
	@ echo "Compiling $<"
	@ $(CXX) -c $(CFLAGS) -o $@ $(filter %.cc,$^)

$(TEST_DIR)/$(BUILD_DIR)/%.o: src/%.c $(HEADER_OBJS) | $(TEST_DIR)/$(BUILD_DIR)
	@ echo "Compiling $<"
	@ $(CC) -c $(CFLAGS) -o $@ $(filter %.c,$^)

$(TEST_DIR)/$(BUILD_DIR)/$(TEST_BINARY): $(TEST_OBJS) $(HEADER_OBJS) $(BUILD_DIR)/lib/$(OUTPUT_NAME) | $(TEST_DIR)/$(BUILD_DIR)
	@ echo "Linking $@"
	@ $(CXX) $(filter %.o,$^) -L${BUILD_DIR}/lib -Wl,-rpath,${BUILD_DIR}/lib -latom -lgtest_main -lgtest $(LDFLAGS) -o $@

.PHONY: all
all: $(BUILD_DIR)/lib/$(OUTPUT_NAME)

.PHONY: install
install: $(BUILD_DIR)/lib/$(OUTPUT_NAME)
	mkdir -p $(PREFIX)/$(INSTALL_DIR)/inc
	mkdir -p $(PREFIX)/$(INSTALL_DIR)/lib
	cp -r $(BUILD_DIR)/inc/*.h $(PREFIX)/$(INSTALL_DIR)/inc
	cp -r $(BUILD_DIR)/lib/*.so $(PREFIX)/$(INSTALL_DIR)/lib

.PHONY: test
test: $(TEST_DIR)/$(BUILD_DIR)/$(TEST_BINARY)
	./$(TEST_DIR)/$(BUILD_DIR)/$(TEST_BINARY) --gtest_filter=$(TEST_FILTER)

.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)
	rm -rf $(TEST_DIR)/$(BUILD_DIR)
