{
  writeShellScriptBin,
  ccf-sandbox,
  lskv,
}: let
  ls = enclave: let
    enclave_type =
      if enclave == "virtual"
      then "virtual"
      else "release";
    l = lskv.${enclave};
    sandbox = ccf-sandbox.${enclave};
  in
    writeShellScriptBin "lskv-sandbox.sh" ''
      ${sandbox}/bin/sandbox.sh --package ${l}/lib/liblskv --enclave-type ${enclave_type} --enclave-platform ${enclave} $@
    '';
in {
  virtual = ls "virtual";
  sgx = ls "sgx";
}
