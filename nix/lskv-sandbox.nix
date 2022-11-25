{
  writeShellScriptBin,
  ccf-sandbox,
  lskv,
  platform ? "virtual",
}: let
  enclave_type =
    if platform == "virtual"
    then "virtual"
    else "release";
  l = lskv.override {inherit platform;};
  sandbox = ccf-sandbox.override {inherit platform;};
in
  writeShellScriptBin "lskv-sandbox.sh" ''
    ${sandbox}/bin/sandbox.sh --package ${l}/lib/liblskv --enclave-type ${enclave_type} --enclave-platform ${platform} $@
  ''
