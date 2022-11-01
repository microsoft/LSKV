{
  writeShellScriptBin,
  ccf-sandbox,
  lskv,
}: {enclave}: let
  enclave_type =
    if enclave == "virtual"
    then "virtual"
    else "release";
  l = lskv {inherit enclave;};
  sandbox = ccf-sandbox {inherit enclave;};
in
  writeShellScriptBin "lskv-sandbox.sh" ''
    ${sandbox}/bin/sandbox.sh -p ${l}/lib/liblskv --enclave-type ${enclave_type} $@
  ''
