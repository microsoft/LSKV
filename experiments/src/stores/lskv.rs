use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::path::PathBuf;
use std::process::Child;
use std::process::Command;
use std::time::Duration;

pub struct LskvStore {
    pub nodes: Vec<String>,
    pub enclave: String,
    pub worker_threads: u32,
    pub sig_tx_interval: u32,
    pub sig_ms_interval: u32,
    pub ledger_chunk_bytes: u32,
    pub snapshot_tx_interval: u32,
    pub workspace: PathBuf,
    pub http_version: u8,
    pub tmpfs: bool,
}

impl LskvStore {
    pub fn run(&self, root_dir: &Path) -> Child {
        let mut args = vec![
            "benchmark/lskv_cluster.py".to_owned(),
            "--enclave".to_owned(),
            self.enclave.clone(),
            "--worker-threads".to_owned(),
            self.worker_threads.to_string(),
            "--sig-tx-interval".to_owned(),
            self.sig_tx_interval.to_string(),
            "--sig-ms-interval".to_owned(),
            self.sig_ms_interval.to_string(),
            "--ledger-chunk-bytes".to_owned(),
            self.ledger_chunk_bytes.to_string(),
            "--snapshot-tx-interval".to_owned(),
            self.snapshot_tx_interval.to_string(),
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
        Command::new("python3")
            .args(args)
            .current_dir(root_dir)
            .spawn()
            .unwrap()
    }

    pub async fn wait_for_ready(&self) {
        println!("waiting for ready");
        for _ in 0..1000 {
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
        println!("checking node {} is ready", node);
        #[derive(Debug, serde::Deserialize)]
        struct NetworkResponse {
            service_status: String,
        }

        let ca = self.workspace.join("common").join("service_cert.pem");
        let mut ca_contents = Vec::new();
        if !ca.is_file() {
            println!("ca file does not exist {:?}", ca);
            return false;
        }
        File::open(ca)
            .and_then(|mut f| f.read_to_end(&mut ca_contents))
            .unwrap();
        let certificate = reqwest::tls::Certificate::from_pem(&ca_contents).unwrap();
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
            println!("Failed sending request {:?}", res);
            return false;
        }
        let res = res.unwrap();
        if res.status() == 200 {
            let res = res.json::<NetworkResponse>().await.unwrap();
            if res.service_status == "Open" {
                return true;
            }
        }
        false
    }
}
