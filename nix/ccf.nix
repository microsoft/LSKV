{
  fetchFromGitHub,
  cmake,
  ninja,
  stdenv,
  openenclave,
  libuv,
  az-dcap,
  sgx-dcap,
  sgx-psw,
  makeWrapper,
  protobuf,
  arrow-cpp,
}: let
  ccf = enclave:
    stdenv.mkDerivation rec {
      pname = "ccf-${enclave}";
      version = "4.0.0-dev0";
      src = fetchFromGitHub {
        owner = "microsoft";
        repo = "CCF";
        name = "ccf-${version}";
        rev = "ccf-${version}";
        hash = "sha256-pnopMvATNoQxEJ68wA+A6eLqFVnxBHkdOUNcJXi+Abs=";
      };
      patches = [
        patches/ccf-no-python.diff
        patches/ccf-no-python-pb2.diff
        patches/ccf-protoc-binary.diff
        patches/ccf-ignore-submitter.diff
      ];

      nativeBuildInputs = [
        cmake
        ninja
        libuv
        protobuf
        arrow-cpp
        sgx-dcap
        openenclave
        makeWrapper
      ];

      cmakeFlags = [
        "-DBUILD_TESTS=OFF"
        "-DBUILD_UNIT_TESTS=OFF"
        "-DLVI_MITIGATIONS=OFF"
        "-DCOMPILE_TARGET=${enclave}"
      ];

      NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
      NIX_NO_SELF_RPATH = "1";

      postInstall = ''
        wrapProgram $out/bin/cchost \
          --suffix LD_LIBRARY_PATH ':' "${az-dcap}/lib:${sgx-psw}/lib:${sgx-dcap}/lib"

        # These are signed with a randomly generated key, which makes the build non-reproducible
        rm -f $out/lib/libjs_generic.enclave.so.debuggable \
           $out/lib/libjs_generic.enclave.so.signed
      '';
    };
in {
  virtual = ccf "virtual";
  sgx = ccf "sgx";
}
