# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
BUILD=build
CCF_PREFIX_VIRTUAL=/opt/ccf_virtual
CCF_PREFIX_SGX=/opt/ccf_sgx

CC!=which clang-15
CXX!=which clang++-15

OE_CC!=which clang-11
OE_CXX!=which clang++-11

ETCD_VER=v3.5.4
ETCD_DOWNLOAD_URL=https://github.com/etcd-io/etcd/releases/download

CPP_FILES=$(wildcard src/**/*.cpp)
H_FILES=$(wildcard src/**/*.h)

BIN_DIR=bin

CCF_VER=ccf-4.0.7
CCF_VER_LOWER=ccf_virtual_4.0.7
CCF_SGX_VER_LOWER=ccf_sgx_4.0.7
CCF_SGX_UNSAFE_VER_LOWER=ccf_sgx_unsafe_4.0.7

.PHONY: install-ccf-virtual
install-ccf-virtual:
	wget -c https://github.com/microsoft/CCF/releases/download/$(CCF_VER)/$(CCF_VER_LOWER)_amd64.deb # download deb
	sudo apt install ./$(CCF_VER_LOWER)_amd64.deb # Installs CCF under /opt/ccf_virtual
	/opt/ccf_virtual/getting_started/setup_vm/run.sh /opt/ccf_virtual/getting_started/setup_vm/app-dev.yml --extra-vars "platform=virtual"  # Install dependencies

.PHONY: install-ccf-sgx
install-ccf-sgx:
	wget -c https://github.com/microsoft/CCF/releases/download/$(CCF_VER)/$(CCF_SGX_VER_LOWER)_amd64.deb # download deb
	sudo apt install ./$(CCF_SGX_VER_LOWER)_amd64.deb # Installs CCF under /opt/ccf_sgx
	/opt/ccf_sgx/getting_started/setup_vm/run.sh /opt/ccf_sgx/getting_started/setup_vm/app-dev.yml --extra-vars "platform=sgx" # Install dependencies

.PHONY: install-ccf-sgx-unsafe
install-ccf-sgx-unsafe:
	wget -c https://github.com/microsoft/CCF/releases/download/$(CCF_VER)/$(CCF_SGX_UNSAFE_VER_LOWER)_amd64.deb # download deb
	sudo apt install ./$(CCF_SGX_UNSAFE_VER_LOWER)_amd64.deb # Installs CCF under /opt/ccf_sgx_unsafe
	/opt/ccf_sgx_unsafe/getting_started/setup_vm/run.sh /opt/ccf_sgx_unsafe/getting_started/setup_vm/app-dev.yml --extra-vars "platform=sgx" # Install dependencies

.PHONY: build-virtual
build-virtual: .venv
	mkdir -p $(BUILD)
	cd $(BUILD) && CC=$(CC) CXX=$(CXX) cmake -DCOMPILE_TARGET=virtual -DCMAKE_EXPORT_COMPILE_COMMANDS=1 -DVERBOSE_LOGGING=OFF -DCCF_UNSAFE=OFF -DGENERATE_PYTHON=ON -GNinja ..
	. .venv/bin/activate && cd $(BUILD) && ninja

.PHONY: build-virtual-verbose
build-virtual-verbose:
	mkdir -p $(BUILD)
	cd $(BUILD) && CC=$(CC) CXX=$(CXX) cmake -DCOMPILE_TARGET=virtual -DCMAKE_EXPORT_COMPILE_COMMANDS=1 -DVERBOSE_LOGGING=ON -DCCF_UNSAFE=OFF -DGENERATE_PYTHON=ON -GNinja ..
	cd $(BUILD) && ninja

.PHONY: build-sgx
build-sgx: .venv
	mkdir -p $(BUILD)
	cd $(BUILD) && CC=$(OE_CC) CXX=$(OE_CXX) cmake -DCOMPILE_TARGET=sgx -DCMAKE_EXPORT_COMPILE_COMMANDS=1 -DVERBOSE_LOGGING=OFF -DCCF_UNSAFE=OFF -DGENERATE_PYTHON=ON -GNinja ..
	. .venv/bin/activate && cd $(BUILD) && ninja

.PHONY: build-docker-virtual
build-docker-virtual:
	docker build -t lskv:latest-virtual -f Dockerfile.virtual .

.PHONY: build-docker-sgx
build-docker-sgx:
	docker build -t lskv:latest-sgx -f Dockerfile.sgx .

.PHONY: build-docker
build-docker: build-docker-virtual build-docker-sgx

.PHONY: run-docker-virtual
run-docker-virtual: .venv
	. .venv/bin/activate && python3 benchmark/lskv_cluster.py --enclave virtual

.PHONY: run-docker-sgx
run-docker-sgx: .venv
	. .venv/bin/activate && python3 benchmark/lskv_cluster.py --enclave sgx

.PHONY: debug-dockerignore
debug-dockerignore:
	docker build --no-cache -t build-context -f Dockerfile.ignore .
	docker run --rm build-context

.PHONY: run-virtual
run-virtual: build-virtual
	VENV_DIR=.venv $(CCF_PREFIX_VIRTUAL)/bin/sandbox.sh -p $(BUILD)/liblskv.virtual.so -e virtual -t virtual --http2

.PHONY: run-virtual-verbose
run-virtual-verbose: build-virtual-verbose
	VENV_DIR=.venv $(CCF_PREFIX_VIRTUAL)/bin/sandbox.sh -p $(BUILD)/liblskv.virtual.so -e virtual -t virtual --http2

.PHONY: run-virtual-http1
run-virtual-http1: build-virtual
	VENV_DIR=.venv $(CCF_PREFIX_VIRTUAL)/bin/sandbox.sh -p $(BUILD)/liblskv.virtual.so -e virtual -t virtual

.PHONY: run-virtual-verbose-http1
run-virtual-verbose-http1: build-virtual-verbose
	VENV_DIR=.venv $(CCF_PREFIX_VIRTUAL)/bin/sandbox.sh -p $(BUILD)/liblskv.virtual.so -e virtual -t virtual

.PHONY: run-sgx
run-sgx: build-sgx
	VENV_DIR=.venv $(CCF_PREFIX_SGX)/bin/sandbox.sh -p $(BUILD)/liblskv.enclave.so.signed -e release -t sgx --http2

.PHONY: test-etcd-integration
test-etcd-integration: build-virtual patched-etcd
	./integration-tests.sh -v

.PHONY: tests
tests: build-virtual .venv
	. .venv/bin/activate && pytest -v

.PHONY: patched-etcd
patched-etcd:
	rm -rf $(BUILD)/3rdparty/etcd
	mkdir -p $(BUILD)/3rdparty
	cp -r 3rdparty/etcd $(BUILD)/3rdparty/.
	git apply --directory=$(BUILD)/3rdparty/etcd patches/0001-etcd-patches.patch

.PHONY: patched-k6
patched-k6:
	rm -rf $(BUILD)/3rdparty/k6
	mkdir -p $(BUILD)/3rdparty
	cp -r 3rdparty/k6 $(BUILD)/3rdparty/.
	git apply --directory=$(BUILD)/3rdparty/k6 patches/k6-micro.diff

$(BIN_DIR)/benchmark: patched-etcd
	cd $(BUILD)/3rdparty/etcd && go build -buildvcs=false ./tools/benchmark
	mkdir -p $(BIN_DIR)
	mv $(BUILD)/3rdparty/etcd/benchmark $(BIN_DIR)/benchmark

$(BIN_DIR)/etcd:
	rm -f /tmp/etcd-$(ETCD_VER)-linux-amd64.tar.gz
	rm -rf /tmp/etcd-download-test && mkdir -p /tmp/etcd-download-test
	curl -L $(ETCD_DOWNLOAD_URL)/$(ETCD_VER)/etcd-$(ETCD_VER)-linux-amd64.tar.gz -o /tmp/etcd-$(ETCD_VER)-linux-amd64.tar.gz
	tar xzvf /tmp/etcd-$(ETCD_VER)-linux-amd64.tar.gz -C /tmp/etcd-download-test --strip-components=1
	rm -f /tmp/etcd-$(ETCD_VER)-linux-amd64.tar.gz
	mkdir -p $(BIN_DIR)
	mv /tmp/etcd-download-test/etcdctl $(BIN_DIR)/etcdctl
	mv /tmp/etcd-download-test/etcd $(BIN_DIR)/etcd

$(BIN_DIR)/etcdctl: $(BIN_DIR)/etcd

.PHONY: $(BIN_DIR)/go-ycsb
$(BIN_DIR)/go-ycsb:
	cd 3rdparty/go-ycsb && make && mv bin/go-ycsb ../../bin/.

$(BIN_DIR)/k6: patched-k6
	cd $(BUILD)/3rdparty/k6 && go build -buildvcs=false
	mkdir -p $(BIN_DIR)
	mv $(BUILD)/3rdparty/k6/k6 $(BIN_DIR)/k6

.PHONY: .venv
.venv: requirements.txt
	python3 -m venv .venv
	. .venv/bin/activate && pip3 install -r requirements.txt

.PHONY: notebook
notebook: .venv
	. .venv/bin/activate && jupyter notebook

.PHONY: execute-notebook
execute-notebook: .venv
	. .venv/bin/activate && jupyter nbconvert --execute --to notebook --inplace benchmark/etcd-analysis.ipynb
	. .venv/bin/activate && jupyter nbconvert --execute --to notebook --inplace benchmark/ycsb-analysis.ipynb
	. .venv/bin/activate && jupyter nbconvert --execute --to notebook --inplace benchmark/perf-analysis.ipynb
	. .venv/bin/activate && jupyter nbconvert --execute --to notebook --inplace benchmark/k6-analysis.ipynb

.PHONY: clear-notebook
clear-notebook: .venv
	. .venv/bin/activate && jupyter nbconvert --clear-output **/*.ipynb

$(BIN_DIR)/cfssl:
	mkdir -p $(BIN_DIR)
	curl -s -L -o $(BIN_DIR)/cfssl https://pkg.cfssl.org/R1.2/cfssl_linux-amd64
	curl -s -L -o $(BIN_DIR)/cfssljson https://pkg.cfssl.org/R1.2/cfssljson_linux-amd64
	chmod +x $(BIN_DIR)/cfssl
	chmod +x $(BIN_DIR)/cfssljson

$(BIN_DIR)/cfssljson: $(BIN_DIR)/cfssl

.PHONY: cpplint
cpplint: $(CPP_FILES) $(H_FILES)
	cpplint --filter=-whitespace/braces,-whitespace/indent,-whitespace/comments,-whitespace/newline,-build/include_order,-build/include_subdir,-runtime/references,-runtime/indentation_namespace $(CPP_FILES) $(H_FILES)

.PHONY: clean
clean:
	rm -rf $(BUILD)
