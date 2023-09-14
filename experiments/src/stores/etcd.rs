use std::fs::File;
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {}

pub struct EtcdStore {
    pub config: Config,
    pub nodes: Vec<String>,
    pub configuration_dir: PathBuf,
    pub workspace: PathBuf,
    pub tmpfs: bool,
}

impl EtcdStore {
    pub fn run(&self, root_dir: &Path) -> Child {
        let mut args = vec![
            "benchmark/etcd_cluster.py".to_owned(),
            "--workspace".to_owned(),
            self.workspace.to_string_lossy().into_owned(),
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
        struct HealthResponse {
            health: String,
        }

        let address: Url = node.parse().unwrap();
        let address = format!(
            "{}:{}",
            address.host().unwrap(),
            address.port().unwrap() + 2
        );

        let client = reqwest::Client::builder().build().unwrap();
        let res = client
            .get(format!("http://{}/health", address))
            .send()
            .await;
        if res.is_err() {
            debug!("Failed sending request {:?}", res);
            return false;
        }
        let res = res.unwrap();
        if res.status().is_success() {
            let res = res.json::<HealthResponse>().await.unwrap();
            if res.health == "true" {
                info!("Node {node} is ready");
                return true;
            } else {
                debug!("Node not ready but responded to health check {:?}", res)
            }
        }
        false
    }

    pub fn get_leader_address(&self, root_dir: &Path) -> String {
        let node = self.nodes.first().unwrap();
        let address: Url = node.parse().unwrap();
        let address = format!(
            "https://{}:{}",
            address.host().unwrap(),
            address.port().unwrap()
        );

        let args = [
            "--endpoints".to_owned(),
            address,
            "--cacert".to_owned(),
            self.cacert().to_string_lossy().into_owned(),
            "--cert".to_owned(),
            self.cert().to_string_lossy().into_owned(),
            "--key".to_owned(),
            self.key().to_string_lossy().into_owned(),
            "endpoint".to_owned(),
            "status".to_owned(),
            "-w".to_owned(),
            "json".to_owned(),
            "--cluster".to_owned(),
        ];

        #[derive(Debug, serde::Deserialize)]
        struct Header {
            member_id: u64,
        }

        #[derive(Debug, serde::Deserialize)]
        struct Status {
            header: Header,
            leader: u64,
        }

        #[derive(Debug, serde::Deserialize)]
        struct EndpointStatusResponse {
            #[serde(rename = "Status")]
            status: Status,
            #[serde(rename = "Endpoint")]
            endpoint: String,
        }

        let res = Command::new("bin/etcdctl")
            .args(args)
            .current_dir(root_dir)
            .output()
            .unwrap();
        let out = serde_json::from_slice::<Vec<EndpointStatusResponse>>(&res.stdout).unwrap();

        for element in out {
            let member_id = element.status.header.member_id;
            let leader = element.status.leader;
            if member_id == leader {
                let addr = element.endpoint;
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
