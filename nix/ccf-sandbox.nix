{
  ccf,
  openenclave,
  python3,
  stdenv,
  platform ? "virtual",
  verbose ? false,
}: let
  infra = python3.pkgs.toPythonApplication python3.pkgs.python-ccf-infra;
  c = ccf.override {inherit platform verbose;};
in
  stdenv.mkDerivation {
    pname = "ccf-sandbox-${platform}";
    inherit (c) version src;

    dontBuild = true;

    installPhase = ''
      install -m755 -D ${./ccf-sandbox.sh} $out/bin/sandbox.sh
      install -m644 -t $out/bin \
        samples/constitutions/default/actions.js \
        samples/constitutions/default/validate.js \
        samples/constitutions/sandbox/resolve.js \
        samples/constitutions/default/apply.js

      substituteInPlace $out/bin/sandbox.sh \
        --replace CCF_ROOT "${c}" \
        --replace OE_ROOT "${openenclave}" \
        --replace START_NETWORK_SCRIPT "${infra}/bin/start_network.py"
    '';
  }
