use std::fmt::Display;
use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::path::PathBuf;
use std::process::Child;
use std::process::Command;
use std::time::Duration;

use reqwest::Url;
use serde::Deserialize;
use serde::Serialize;
use tracing::debug;
use tracing::info;

#[derive(Debug, Copy, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Enclave {
    Virtual,
    SGX,
}

impl Display for Enclave {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{}",
            match self {
                Self::Virtual => "virtual",
                Self::SGX => "sgx",
            }
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub enclave: Enclave,
    pub worker_threads: u32,
    pub sig_tx_interval: u32,
    pub sig_ms_interval: u32,
    pub ledger_chunk_bytes: String,
    pub snapshot_tx_interval: u32,
}

pub struct LskvStore {
    pub config: Config,
    pub nodes: Vec<String>,
    pub configuration_dir: PathBuf,
    pub workspace: PathBuf,
    pub http_version: u8,
    pub tmpfs: bool,
}

impl LskvStore {
    pub fn run(&self, root_dir: &Path) -> Child {
        let mut args = vec![
            "benchmark/lskv_cluster.py".to_owned(),
            "--enclave".to_owned(),
            self.config.enclave.to_string(),
            "--worker-threads".to_owned(),
            self.config.worker_threads.to_string(),
            "--sig-tx-interval".to_owned(),
            self.config.sig_tx_interval.to_string(),
            "--sig-ms-interval".to_owned(),
            self.config.sig_ms_interval.to_string(),
            "--ledger-chunk-bytes".to_owned(),
            self.config.ledger_chunk_bytes.clone(),
            "--snapshot-tx-interval".to_owned(),
            self.config.snapshot_tx_interval.to_string(),
            "--workspace".to_owned(),
            self.workspace.to_string_lossy().into_owned(),
            "--http-version".to_owned(),
            self.http_version.to_string(),
        ];
        if self.tmpfs {
            args.push("--tmpfs".to_owned());
        }
        for node in &self.nodes {
            args.push("--node".to_owned());
            args.push(node.to_owned());
        }
        let out_file = File::create(self.configuration_dir.join("runner.out")).unwrap();
        let err_file = File::create(self.configuration_dir.join("runner.err")).unwrap();
        Command::new("python3")
            .args(args)
            .stdout(out_file)
            .stderr(err_file)
            .current_dir(root_dir)
            .spawn()
            .unwrap()
    }

    pub async fn wait_for_ready(&self) {
        debug!("waiting for ready");
        for _ in 0..100 {
            let mut all = true;
            for node in &self.nodes {
                if !self.is_ready(node).await {
                    all = false;
                    break;
                }
            }
            if all {
                break;
            }
            tokio::time::sleep(Duration::from_millis(1000)).await;
        }
    }

    async fn is_ready(&self, node: &str) -> bool {
        debug!("Checking node {node} is ready");
        #[derive(Debug, serde::Deserialize)]
        struct NetworkResponse {
            service_status: String,
        }

        let ca = self.workspace.join("common").join("service_cert.pem");
        let mut ca_contents = Vec::new();
        if !ca.is_file() {
            debug!("ca file does not exist {:?}", ca);
            return false;
        }
        match File::open(ca).and_then(|mut f| f.read_to_end(&mut ca_contents)) {
            Ok(_) => {}
            Err(_) => return false,
        };
        let certificate = match reqwest::tls::Certificate::from_pem(&ca_contents) {
            Ok(c) => c,
            Err(_) => return false,
        };
        let address = node
            .split("://")
            .skip(1)
            .map(|s| s.to_owned())
            .collect::<Vec<String>>()
            .join("");
        let client = reqwest::Client::builder()
            // CCF doesn't currently support ALPN
            // https://github.com/microsoft/CCF/issues/4814
            .http2_prior_knowledge()
            .add_root_certificate(certificate)
            .build()
            .unwrap();
        let res = client
            .get(format!("https://{}/node/network", address))
            .send()
            .await;
        if res.is_err() {
            debug!("Failed sending request {:?}", res);
            return false;
        }
        let res = res.unwrap();
        if res.status() == 200 {
            let res = res.json::<NetworkResponse>().await.unwrap();
            if res.service_status == "Open" {
                info!("Node {node} is ready");
                return true;
            }
        }
        false
    }

    pub fn get_leader_address(&self) -> String {
        let node = self.nodes.first().unwrap();
        let address: Url = node.parse().unwrap();
        let address = format!(
            "https://{}:{}",
            address.host().unwrap(),
            address.port().unwrap()
        );

        let args = [
            "--cacert".to_owned(),
            self.cacert().to_string_lossy().into_owned(),
            "--cert".to_owned(),
            self.cert().to_string_lossy().into_owned(),
            "--key".to_owned(),
            self.key().to_string_lossy().into_owned(),
            format!("{address}/node/network/nodes"),
        ];

        #[derive(Debug, serde::Deserialize)]
        struct RpcInterface {
            published_address: String,
        }

        #[derive(Debug, serde::Deserialize)]
        struct RpcInterfaces {
            primary_rpc_interface: RpcInterface,
        }

        #[derive(Debug, serde::Deserialize)]
        struct Node {
            primary: bool,
            rpc_interfaces: RpcInterfaces,
        }

        #[derive(Debug, serde::Deserialize)]
        struct EndpointStatusResponse {
            nodes: Vec<Node>,
        }

        let res = Command::new("curl").args(args).output().unwrap();
        let out = serde_json::from_slice::<EndpointStatusResponse>(&res.stdout).unwrap();

        for element in out.nodes {
            let primary = element.primary;
            if primary {
                let addr = element
                    .rpc_interfaces
                    .primary_rpc_interface
                    .published_address;
                let addr = format!("https://{addr}");
                info!(?addr, "Found leader address");
                return addr;
            }
        }

        return node.to_owned();
    }

    pub fn cacert(&self) -> PathBuf {
        self.workspace
            .join("common")
            .join("service_cert.pem")
            .canonicalize()
            .unwrap()
    }

    pub fn cert(&self) -> PathBuf {
        self.workspace
            .join("common")
            .join("user0_cert.pem")
            .canonicalize()
            .unwrap()
    }

    pub fn key(&self) -> PathBuf {
        self.workspace
            .join("common")
            .join("user0_privk.pem")
            .canonicalize()
            .unwrap()
    }
}
