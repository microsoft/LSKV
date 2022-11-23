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
  version = "0.9.dev8";
  src = fetchFromGitHub {
    owner = "TimothyClaeys";
    repo = "pycose";
    rev = "v${version}";
    hash = "sha256-/jwq2C2nvHInsgPG4jZCr+XsvlUJdYewAkasrUPVaHM=";
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
