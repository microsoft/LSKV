{
  fetchFromGitHub,
  stdenv,
  cmake,
  sgx-dcap,
  openenclave,
  ninja,
  protobuf,
  ccf,
  nix-filter,
}: {enclave}:
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
  ];

  buildInputs = [
    (ccf {inherit enclave;})
    openenclave
    protobuf
    sgx-dcap
  ];

  cmakeFlags = [
    "-DLVI_MITIGATIONS=OFF"
    "-DCOMPILE_TARGET=${enclave}"
  ];

  NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
  NIX_NO_SELF_RPATH = "1";
}
