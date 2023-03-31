{
  writeShellScriptBin,
  ccf-sandbox,
  lskv,
  platform ? "virtual",
  verbose ? false,
}: let
  enclave_type =
    if platform == "virtual"
    then "virtual"
    else "release";
  l = lskv.override {inherit platform verbose;};
  sandbox = ccf-sandbox.override {inherit platform verbose;};
in
  writeShellScriptBin "lskv-sandbox.sh" ''
    ${sandbox}/bin/sandbox.sh --package ${l}/lib/liblskv --enclave-type ${enclave_type} --enclave-platform ${platform} --http2 $@
  ''
