{ fetchFromGitHub
, stdenv
, curl
, nlohmann_json
, makeWrapper
, fetchurl
, lib
, openssl_1_1
}:
let
  fetchFromIntelGitHub = { path, ... }@attrs: fetchurl ({
    url = "https://raw.githubusercontent.com/intel/${path}";
  } // removeAttrs attrs [ "path" ]);

  files = [
    (fetchFromIntelGitHub {
      path = "SGXDataCenterAttestationPrimitives/0436284f12f1bd5da7e7a06f6274d36b4c8d39f9/QuoteGeneration/quote_wrapper/common/inc/sgx_ql_lib_common.h";
      hash = "sha256-36oxPBt0SmmRqjwtXgP87wOY2tOlbxQEhMZZgjoh4xI=";
    })
    (fetchFromIntelGitHub {
      path = "linux-sgx/1ccf25b64abd1c2eff05ead9d14b410b3c9ae7be/common/inc/sgx_report.h";
      hash = "sha256-NCDH3uhSlRRx0DDA/MKhWlUnA1rJ94O4DLuzqmnfr0I=";
    })
    (fetchFromIntelGitHub {
      path = "linux-sgx/1ccf25b64abd1c2eff05ead9d14b410b3c9ae7be/common/inc/sgx_key.h";
      hash = "sha256-3ApIE2QevE8MeU0y5UGvwaKD9OOJ3H9c5ibxsBSr49g=";
    })
    (fetchFromIntelGitHub {
      path = "linux-sgx/1ccf25b64abd1c2eff05ead9d14b410b3c9ae7be/common/inc/sgx_attributes.h";
      hash = "sha256-fPuwchUP9L1Zi3BoFfhmRPe7CgjHlafNrKeZDOF2l1k=";
    })
  ];
in
stdenv.mkDerivation rec {
  pname = "az-dcap";
  version = "1.11.2";
  src = fetchFromGitHub {
    owner = "microsoft";
    repo = "Azure-DCAP-Client";
    rev = version;
    hash = "sha256-EYj3jnzTyJRl6N7avNf9VrB8r9U6zIE6wBNeVsMtWCA=";
  };
  nativeBuildInputs = [ makeWrapper ];
  buildInputs = [ 
    (curl.override{openssl=openssl_1_1;} )
    nlohmann_json 
    ];

  configurePhase = ''
    cd src/Linux
    cat Makefile.in | sed "s|##CURLINC##|${curl.dev}/include/curl|g" > Makefile
    ${lib.flip (lib.concatMapStringsSep "\n") files (f: "cp ${f} ${f.name}")}
  '';
  makeFlags = [ "prefix=$(out)" ];
}
