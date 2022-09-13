BUILD=build
CCF_PREFIX=/opt/ccf

CC="/opt/oe_lvi/clang-10"
CXX="/opt/oe_lvi/clang++-10"

.PHONY: build-virtual
build-virtual:
	mkdir -p $(BUILD)
	cd $(BUILD)
	cd $(BUILD) && CC=$(CC) CXX=$(CXX) cmake -DCOMPILE_TARGETS=virtual -DCMAKE_EXPORT_COMPILE_COMMANDS=1 -GNinja ..
	cd $(BUILD) && ninja

.PHONY: run-virtual
run-virtual: build-virtual
	$(CCF_PREFIX)/bin/sandbox.sh -p $(BUILD)/libccf_kvs.virtual.so --http2

.PHONY: test-virtual
test-virtual: build-virtual
	3rdparty/etcd/tests/ccf-kvs.sh

.PHONY: clean
clean:
	rm -rf $(BUILD)
