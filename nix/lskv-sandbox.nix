{
  writeShellScriptBin,
  ccf-sandbox,
  lskv,
}:
writeShellScriptBin "lskv-sandbox.sh" ''
  ${ccf-sandbox}/bin/sandbox.sh -p ${lskv}/lib/liblskv.virtual.so $@
''
