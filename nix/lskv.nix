{ fetchFromGitHub
, stdenv
, cmake
, openenclave
, ninja
, protobuf
, ccf
}:
stdenv.mkDerivation rec {
  pname = "lskv";
  version = "0.1.0";
  src = ./..;

  nativeBuildInputs = [ cmake ninja 
  ccf 
  openenclave
  protobuf
  ];

  cmakeFlags = [
    "-DLVI_MITIGATIONS=OFF"
    "-DCOMPILE_TARGETS=virtual"
  ];

  NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
}
