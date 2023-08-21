{
  stdenv,
  fetchurl,
  fetchzip,
  openenclave-version,
  openenclave-src,
  cmake,
  ninja,
  perl,
  openssl,
}: let
  sgx-h = fetchurl {
    url = "https://raw.githubusercontent.com/torvalds/linux/v5.13/arch/x86/include/uapi/asm/sgx.h";
    sha256 = "4764b8ce858579d99f1b66bb1e5f04ba149a38aea15649fff19f65f8d9113fd0";
  };
  compiler-rt = fetchzip {
    url = "https://github.com/llvm/llvm-project/releases/download/llvmorg-11.1.0/compiler-rt-11.1.0.src.tar.xz";
    hash = "sha256-jycaXF3wGF85B2cwe+1q5fVPhR+/JnaZ+4A8y/qyBag=";
  };
  libcxx = fetchzip {
    url = "https://github.com/llvm/llvm-project/releases/download/llvmorg-11.1.0/libcxx-11.1.0.src.tar.xz";
    sha256 = "sha256-UoRPugdPj0FtKp79V1nljehWyhChxgUo3mb/Wyq/RIA=";
  };
  symcrypt = fetchzip {
    url = "https://github.com/microsoft/SymCrypt/releases/download/v103.0.1/symcrypt-linux-oe_full-AMD64-103.0.1-69dbff3.tar.gz";
    sha256 = "sha256-VCJlAOnbY2kYlnNv6SxumD4BinntAvpBFkUs9hBxCY4=";
    stripRoot = false;
  };
in
  stdenv.mkDerivation rec {
    pname = "openenclave";
    version = openenclave-version;
    src = openenclave-src;
    patches = [
      # patches/openenclave.diff
      patches/openenclave-pkgconfig.diff
    ];
    cmakeFlags = [
      "-DCMAKE_BUILD_TYPE=RelWithDebInfo"
      "-DFETCHCONTENT_SOURCE_DIR_COMPILER-RT-SOURCES=${compiler-rt}"
      "-DFETCHCONTENT_SOURCE_DIR_LIBCXX_SOURCES=${libcxx}"
      "-DFETCHCONTENT_SOURCE_DIR_SYMCRYPT_PACKAGE=${symcrypt}"
      "-DCLANG_INTRINSIC_HEADERS_DIR=${toString stdenv.cc.cc.lib}/lib/clang/${stdenv.cc.version}/include"
      "-DENABLE_REFMAN=OFF"
      "-DBUILD_TESTS=OFF"

      # oeutil includes an enclave (oeutil_enc), which is signed with a random key.
      # This breaks reproducible builds.
      "-DBUILD_OEUTIL_TOOL=OFF"

      # "-DCMAKE_BUILD_WITH_INSTALL_RPATH:BOOL=ON"
      # "-DCMAKE_INSTALL_RPATH_USE_LINK_PATH:BOOL=ON"
    ];

    preConfigure = ''
      mkdir -p build/host
      mkdir -p build/3rdparty/symcrypt_engine
      cp ${sgx-h} build/host/sgx.h
      ln -s ${compiler-rt} 3rdparty/compiler-rt/compiler-rt
      ln -s ${libcxx} 3rdparty/libcxx/libcxx
      ln -s ${symcrypt} build/3rdparty/symcrypt_engine/SymCrypt

      patchShebangs tools/oeutil/gen_pubkey_header.sh
      substituteInPlace tools/oeutil/gen_pubkey_header.sh --replace '/var/tmp/oeutil_lock' '.oeutil_lock'
      patchShebangs 3rdparty/openssl/append-unsupported
      patchShebangs 3rdparty/musl/append-deprecations
    '';

    postFixup = ''
      substituteInPlace $out/lib/${pname}/cmake/${pname}-*.cmake \
        --replace 'set(_IMPORT_PREFIX' '#set(_IMPORT_PREFIX'
    '';

    nativeBuildInputs = [cmake ninja perl];
    propagatedBuildInputs = [openssl];

    # Not sure if we want to keep this
    dontAutoPatchelf = true;

    NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
    NIX_NO_SELF_RPATH = "1";
  }
