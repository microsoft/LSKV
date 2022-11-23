{
  buildPythonPackage,
  GitPython,
  better-exceptions,
  cryptography,
  docker,
  docutils,
  httpx,
  jinja2,
  loguru,
  matplotlib,
  openapi-spec-validator,
  pandas,
  paramiko,
  psutil,
  pyasn1,
  pyjwt,
  pyopenssl,
  grpcio-tools,
  python-ccf,
  cimetrics,
  pycose,
  jwcrypto,
  cbor2,
}:
buildPythonPackage {
  inherit (python-ccf) version src;
  pname = "python-ccf-infra";
  propagatedBuildInputs = [
    python-ccf
    cryptography
    httpx
    psutil
    matplotlib
    loguru
    pandas
    pyasn1
    pyjwt
    paramiko
    jinja2
    docker
    GitPython
    openapi-spec-validator
    better-exceptions
    pyopenssl
    docutils
    grpcio-tools
    cimetrics
    pycose
    jwcrypto
    cbor2
  ] ++ httpx.optional-dependencies.http2;

  preConfigure = ''
    cd tests
    cp ${./ccf_infra_setup.py} setup.py
    sed -i '/python-iptables/d' requirements.txt
    sed -i '/py-spy/d' requirements.txt
    sed -i '/locust/d' requirements.txt

    sed -i '1s|^|#!/usr/bin/env python3\n|' start_network.py
    chmod +x start_network.py
  '';

  doCheck = false;
}
