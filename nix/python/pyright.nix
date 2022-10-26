{
  buildPythonPackage,
  fetchFromGitHub,
}:
buildPythonPackage rec {
  pname = "pyright";
  version = "1.1.267";
  src = fetchFromGitHub {
    owner = "microsoft";
    repo = "pyright";
    rev = version;
    hash = "sha256-VOdr/S/KbnR6X/6U8GH73yKH+l9CYyJ1e4a+C/Q9mxg=";
  };
  sourceRoot = "source/packages/pyright";
}
