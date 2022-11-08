{
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
    protobuf
    sgx-dcap
    (ccf {inherit enclave;})
    openenclave
  ];

  cmakeFlags = [
    "-DCOMPILE_TARGET=${enclave}"
  ];

  NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
  NIX_NO_SELF_RPATH = "1";
}
