{
  fetchFromGitHub,
  stdenv,
  cmake,
  openenclave,
  ninja,
  protobuf,
  ccf,
  nix-filter,
  enclave ? "virtual",
}:
stdenv.mkDerivation rec {
  pname = "lskv-${enclave}";
  version = "0.1.0";
  src = nix-filter {
    root = ./..;
    include = [
      "CMakeLists.txt"
      "oe_sign.conf"
      "src"
      "proto"
    ];
  };

  nativeBuildInputs = [
    cmake
    ninja
    (ccf.override {inherit enclave;})
    openenclave
    protobuf
  ];

  cmakeFlags = [
    "-DLVI_MITIGATIONS=OFF"
    "-DCOMPILE_TARGETS=${enclave}"
  ];

  NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
  NIX_NO_SELF_RPATH = "1";
}
