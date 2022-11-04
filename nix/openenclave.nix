{
  stdenv,
  fetchurl,
  fetchzip,
  fetchFromGitHub,
  cmake,
  ninja,
  perl,
  openssl_1_1,
}: let
  sgx-h = fetchurl {
    url = "https://raw.githubusercontent.com/torvalds/linux/v5.13/arch/x86/include/uapi/asm/sgx.h";
    sha256 = "4764b8ce858579d99f1b66bb1e5f04ba149a38aea15649fff19f65f8d9113fd0";
  };
  compiler-rt = fetchzip {
    url = "https://github.com/llvm/llvm-project/releases/download/llvmorg-10.0.1/compiler-rt-10.0.1.src.tar.xz";
    hash = "sha256-OErVbpYasfvBK0793ujshuHK4tbqq3grQHjYDpebmT4=";
  };
  libcxx = fetchzip {
    url = "https://github.com/llvm/llvm-project/releases/download/llvmorg-10.0.1/libcxx-10.0.1.src.tar.xz";
    sha256 = "sha256-/OhdYPlbNHMxX2VxlurkOspC1OyPDmyUqXvZKxzwkTg=";
  };
  symcrypt = fetchzip {
    url = "https://github.com/microsoft/SymCrypt/releases/download/v101.3.0/symcrypt_AMD64_oe_full_v101.3.0-31e06ae.tgz";
    sha256 = "sha256-diA653HZ4Mn4JbeT6+U0anhP3ySVWZWjcXH7KVVkqkY=";
    stripRoot = false;
  };
in
  stdenv.mkDerivation rec {
    pname = "openenclave";
    version = "0.18.2";
    src = fetchFromGitHub {
      owner = "openenclave";
      repo = "openenclave";
      rev = "v${version}";
      hash = "sha256-VjKrP9dKbCzKZKwypyq+iro2szm1iH8RAynYe5CP0Bc=";
      fetchSubmodules = true;
    };
    patches = [patches/openenclave.diff];
    cmakeFlags = [
      "-DCMAKE_BUILD_TYPE=RelWithDebInfo"
      "-DFETCHCONTENT_SOURCE_DIR_COMPILER-RT-SOURCES=${compiler-rt}"
      "-DFETCHCONTENT_SOURCE_DIR_LIBCXX_SOURCES=${libcxx}"
      "-DFETCHCONTENT_SOURCE_DIR_SYMCRYPT_PACKAGE=${symcrypt}"
      "-DCLANG_INTRINSIC_HEADERS_DIR=${toString stdenv.cc.cc.lib}/lib/clang/10.0.1/include"
      "-DENABLE_REFMAN=OFF"
      "-DBUILD_TESTS=OFF"

      # oeutil includes an enclave (oeutil_enc), which is signed with a random key.
      # This breaks reproducible builds.
      "-DBUILD_OEUTIL_TOOL=OFF"

      "-DCMAKE_BUILD_WITH_INSTALL_RPATH:BOOL=ON"
      "-DCMAKE_INSTALL_RPATH_USE_LINK_PATH:BOOL=ON"
    ];

    preConfigure = ''
      mkdir -p build/host build/3rdparty/symcrypt_engine
      cp ${sgx-h} build/host/sgx.h
      ln -s ${compiler-rt} 3rdparty/compiler-rt/compiler-rt
      ln -s ${libcxx} 3rdparty/libcxx/libcxx
      ln -s ${symcrypt} build/3rdparty/symcrypt_engine/SymCrypt
      patchShebangs tools/oeutil/gen_pubkey_header.sh
      patchShebangs tools/oeapkman/oeapkman
      patchShebangs 3rdparty/openssl/append-unsupported
      patchShebangs 3rdparty/musl/append-deprecations

      substituteInPlace pkgconfig/*.pc --replace \''${prefix}/@CMAKE_INSTALL_LIBDIR@ @CMAKE_INSTALL_LIBDIR@
      substituteInPlace pkgconfig/*.pc --replace \''${prefix}/@CMAKE_INSTALL_INCLUDEDIR@ @CMAKE_INSTALL_INCLUDEDIR@
    '';

    nativeBuildInputs = [cmake ninja perl];
    propagatedBuildInputs = [openssl_1_1];

    # Not sure if we want to keep this
    dontAutoPatchelf = true;

    NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
    NIX_NO_SELF_RPATH = "1";
  }
