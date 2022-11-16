{
  stdenv,
  fetchurl,
  fetchzip,
  fetchFromGitHub,
  cmake,
  ninja,
  perl,
  openssl_1_1,
  clang_10,
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
  oe-version = "0.18.4";
  oe-src = fetchFromGitHub {
    owner = "openenclave";
    repo = "openenclave";
    rev = "v${oe-version}";
    hash = "sha256-65LHXKfDWUvLCMupJkF7o7d6ljsO7nwcmQxRU8H2Xls=";
    fetchSubmodules = true;
  };
  intel-tarball = fetchzip {
    url = "https://download.01.org/intel-sgx/sgx-linux/2.13/as.ld.objdump.gold.r3.tar.gz";
    sha256 = "sha256-gD0LOLebDHZHrV7MW/ApqzdPxazidmDUDqBEnm1JmdQ=";
  };
  lvi-mitigation-bin = stdenv.mkDerivation {
    pname = "lvi-mitigation-bin";
    version = oe-version;
    src = oe-src;

    preConfigure = ''
      patchShebangs scripts/lvi-mitigation/*
      substituteInPlace scripts/lvi-mitigation/install_lvi_mitigation_bindir --replace 'read -rp "Do you want to install in current directory? [yes/no]: " ans' 'ans=yes'
      mkdir -p $out/bin

      ln -s ${intel-tarball} intel-tarball
      ls -lah intel-tarball
      cp intel-tarball/toolset/ubuntu18.04/as $out/bin/as
      cp intel-tarball/toolset/ubuntu18.04/ld $out/bin/ld

      ln -s ${clang_10}/bin/clang $out/bin/clang
      ln -s ${clang_10}/bin/clang++ $out/bin/clang++

      ls -lah $out/bin
    '';

    dontBuild = true;
    dontInstall = true;
  };
in
  stdenv.mkDerivation rec {
    pname = "openenclave";
    version = oe-version;
    src = oe-src;
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

      "-DLVI_MITIGATION=ControlFlow"
      "-DLVI_MITIGATION_BINDIR=/build/source/build/lvi_mitigation_bin"
    ];

    preConfigure = ''
      mkdir -p build/host build/3rdparty/symcrypt_engine
      cp ${sgx-h} build/host/sgx.h
      ln -s ${compiler-rt} 3rdparty/compiler-rt/compiler-rt
      ln -s ${libcxx} 3rdparty/libcxx/libcxx
      ln -s ${symcrypt} build/3rdparty/symcrypt_engine/SymCrypt
      ln -s ${lvi-mitigation-bin}/bin build/lvi_mitigation_bin

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
