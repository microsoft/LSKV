{
  stdenv,
  cmake,
  sgx-dcap,
  openenclave,
  ninja,
  protobuf,
  ccf,
  nix-filter,
  platform ? "virtual",
}:
stdenv.mkDerivation rec {
  pname = "lskv-${platform}";
  version = "0.1.0";
  src = nix-filter {
    root = ./..;
    include = [
      "CMakeLists.txt"
      "cmake"
      "oe_sign.conf"
      "src"
      "proto"
    ];
  };

  nativeBuildInputs = [
    cmake
    ninja
    protobuf
    sgx-dcap
    (ccf.override {inherit platform;})
    openenclave
  ];

  cmakeFlags = [
    "-DCOMPILE_TARGET=${platform}"
    (
      if platform == "sgx"
      then "-DLVI_MITIGATIONS=OFF"
      else null
    )
  ];

  LSKV_VERSION = version;

  NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
  NIX_NO_SELF_RPATH = "1";
}
