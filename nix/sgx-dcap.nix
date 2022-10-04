{ stdenv, fetchFromGitHub, curl, sgx-sdk, protobuf, boost, pkg-config, which, fetchzip }:
let
  version = "1.14";
  prebuilts = fetchzip {
    stripRoot = false;
    url = "https://download.01.org/intel-sgx/sgx-dcap/${version}/linux/prebuilt_dcap_${version}.tar.gz";
    hash = "sha256-aipAa/UxxdGd+P4pv5bO9yDr9oCYvSXQg2/HGVTJMQc=";
  };
in
stdenv.mkDerivation {
  pname = "sgx-dcap";
  inherit version;
  src = fetchFromGitHub {
    owner = "intel";
    repo = "SGXDataCenterAttestationPrimitives";
    rev = "DCAP_${version}";
    hash = "sha256-1r//S2Y98xXV1IhNm5zZ1SruMJXWiyEG52uVWsxLB/I=";
  };

  buildInputs = [ sgx-sdk curl boost ];
  nativeBuildInputs = [ protobuf pkg-config which ];

  # qcnl_wrapper qpl_wrapper qve_wrapper qe3_logic 
  buildPhase = ''
    make -C QuoteGeneration pce_logic qe3_logic
  '';

  installPhase = ''
    mkdir -p $out/lib

    cd QuoteGeneration/build/linux
    cp libsgx_dcap_ql.so $out/lib/libsgx_dcap_ql.so.1.0.0
    ln -s libsgx_dcap_ql.so.1.0.0 $out/lib/libsgx_dcap_ql.so.1
    ln -s libsgx_dcap_ql.so.1.0.0 $out/lib/libsgx_dcap_ql.so

    cp libsgx_pce_logic.so $out/lib/libsgx_pce_logic.so.1.0.0
    ln -s libsgx_pce_logic.so.1.0.0 $out/lib/libsgx_pce_logic.so.1
    ln -s libsgx_pce_logic.so.1.0.0 $out/lib/libsgx_pce_logic.so

    cp libsgx_qe3_logic.so $out/lib/libsgx_qe3_logic.so.1.0.0
    ln -s libsgx_qe3_logic.so.1.0.0 $out/lib/libsgx_qe3_logic.so.1
    ln -s libsgx_qe3_logic.so.1.0.0 $out/lib/libsgx_qe3_logic.so

    cp ${prebuilts}/psw/ae/data/prebuilt/libsgx_pce.signed.so $out/lib
    cp ${prebuilts}/psw/ae/data/prebuilt/libsgx_qe3.signed.so $out/lib
    cp ${prebuilts}/psw/ae/data/prebuilt/libsgx_qve.signed.so $out/lib
    cp ${prebuilts}/psw/ae/data/prebuilt/libsgx_tdqe.signed.so $out/lib
    cp ${prebuilts}/psw/ae/data/prebuilt/libsgx_id_enclave.signed.so $out/lib

    ln -s libsgx_id_enclave.signed.so $out/lib/libsgx_id_enclave.signed.so.1
  '';

  dontFixup = true;
}
