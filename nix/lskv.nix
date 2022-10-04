{ fetchFromGitHub
, stdenv
, cmake
, ninja
, ccf
}:
stdenv.mkDerivation rec {
  pname = "lskv";
  version = "0.1.0";
  src = fetchFromGitHub {
    owner = "microsoft";
    repo = "LSKV";
    name = "lskv-${version}";
    rev = "main";
    hash = "";
  };

  nativeBuildInputs = [ cmake ninja ccf ];

  NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
  NIX_NO_SELF_RPATH = "1";
}
