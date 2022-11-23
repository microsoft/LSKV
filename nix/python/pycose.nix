{
  buildPythonPackage,
  fetchFromGitHub,
  attrs,
  cryptography,
  certvalidator,
  cbor2,
  ecdsa,
  pytest,
}:
buildPythonPackage rec {
  pname = "pycose";
  version = "1.0.1";
  src = fetchFromGitHub {
    owner = "TimothyClaeys";
    repo = "pycose";
    rev = "v${version}";
    hash = "sha256-8d6HebWlSKgx7dmOnT7ZZ5mrMfg6mNWhz1hHPv75XF4=";
  };
  propagatedBuildInputs = [
    attrs
    cryptography
    certvalidator
    cbor2
    ecdsa
    pytest
  ];
}
