{ ccf, openenclave, python3, stdenv }:
let
  infra = python3.pkgs.toPythonApplication (python3.pkgs.python-ccf-infra);
in
stdenv.mkDerivation {
  pname = "ccf-sandbox";
  inherit (ccf) version src;

  installPhase = ''
    install -m755 -D ${./ccf-sandbox.sh} $out/bin/sandbox.sh
    install -m644 -t $out/bin \
      samples/constitutions/default/actions.js \
      samples/constitutions/default/validate.js \
      samples/constitutions/sandbox/resolve.js \
      samples/constitutions/default/apply.js

    substituteInPlace $out/bin/sandbox.sh \
      --replace CCF_ROOT "${ccf}" \
      --replace OE_ROOT "${openenclave}" \
      --replace START_NETWORK_SCRIPT "${infra}/bin/start_network.py"
  '';
}
