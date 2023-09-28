use crate::stores::etcd::EtcdStore;
use crate::stores::lskv::Enclave;
use crate::stores::lskv::LskvStore;
use crate::stores::StoreConfig;
use exp::Environment;
use exp::Experiment;
use futures_util::StreamExt;
use polars::prelude::*;
use std::fs;
use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::path::PathBuf;
use tracing::debug;
use tracing::info;

pub struct YcsbExperiment {
    pub root_dir: PathBuf,
    pub distributed: bool,
}

#[async_trait::async_trait]
impl Experiment for YcsbExperiment {
    type Configuration = Config;

    fn configurations(&mut self) -> Vec<Self::Configuration> {
        let mut configs = Vec::new();
        let mut store_configs = Vec::new();
        store_configs.push(StoreConfig::Etcd(crate::stores::etcd::Config {}));
        let worker_threads = 2;
        let sig_ms_interval = 1_000;
        let sig_tx_interval = 1_000_000; // basically never, just use the timing one
        let ledger_chunk_bytes = "5MB";
        let snapshot_tx_interval = 10;
        let lskv_virtual_config = StoreConfig::Lskv(crate::stores::lskv::Config {
            enclave: Enclave::Virtual,
            worker_threads,
            sig_tx_interval,
            sig_ms_interval,
            ledger_chunk_bytes: ledger_chunk_bytes.to_owned(),
            snapshot_tx_interval,
        });
        let lskv_sgx_config = StoreConfig::Lskv(crate::stores::lskv::Config {
            enclave: Enclave::SGX,
            worker_threads,
            sig_tx_interval,
            sig_ms_interval,
            ledger_chunk_bytes: ledger_chunk_bytes.to_owned(),
            snapshot_tx_interval,
        });
        store_configs.push(lskv_virtual_config.clone());
        store_configs.push(lskv_sgx_config.clone());
        let rate = 10_000;
        for nodes in [3] {
            for workload in [
                YcsbWorkload::A,
                YcsbWorkload::B,
                YcsbWorkload::C,
                YcsbWorkload::D,
                YcsbWorkload::E,
                YcsbWorkload::F,
            ] {
                for store_config in &store_configs {
                    for tmpfs in [false, true] {
                        let config = Config {
                            store_config: store_config.clone(),
                            rate,
                            total: rate * 10,
                            workload,
                            nodes,
                            tmpfs,
                            max_clients: Some(100),
                        };
                        configs.push(config);
                    }
                }
            }
        }
        for nodes in [1, 3, 5, 7] {
            for store_config in [lskv_sgx_config.clone(), lskv_virtual_config.clone()] {
                let config = Config {
                    store_config: store_config.clone(),
                    rate,
                    total: rate * 10,
                    workload: YcsbWorkload::A,
                    nodes,
                    tmpfs: false,
                    max_clients: Some(100),
                };
                configs.push(config);
            }
        }
        for sig_ms_interval in [100, 1000] {
            for store_config in &[lskv_virtual_config.clone(), lskv_sgx_config.clone()] {
                let store_config = match store_config.clone() {
                    StoreConfig::Lskv(mut l) => {
                        l.sig_ms_interval = sig_ms_interval;
                        StoreConfig::Lskv(l)
                    }
                    StoreConfig::Etcd(_) => todo!(),
                };
                let config = Config {
                    store_config,
                    rate,
                    total: rate * 10,
                    workload: YcsbWorkload::A,
                    nodes: 3,
                    tmpfs: false,
                    max_clients: Some(100),
                };
                configs.push(config);
            }
        }
        for worker_threads in [0, 1, 2, 4] {
            for store_config in &[lskv_virtual_config.clone(), lskv_sgx_config.clone()] {
                let store_config = match store_config.clone() {
                    StoreConfig::Lskv(mut l) => {
                        l.worker_threads = worker_threads;
                        StoreConfig::Lskv(l)
                    }
                    StoreConfig::Etcd(_) => todo!(),
                };
                let config = Config {
                    store_config,
                    rate,
                    total: rate * 10,
                    workload: YcsbWorkload::A,
                    nodes: 3,
                    tmpfs: false,
                    max_clients: Some(100),
                };
                configs.push(config);
            }
        }
        configs
    }

    async fn pre_run(&mut self, _configuration: &Self::Configuration) -> exp::ExpResult<()> {
        let experiment_prefix = "apj39-bencher-exp";
        exp::docker_runner::clean(experiment_prefix).await.unwrap();
        Ok(())
    }

    async fn run(
        &mut self,
        configuration: &Self::Configuration,
        configuration_dir: &Path,
    ) -> exp::ExpResult<()> {
        let configuration_dir = configuration_dir.canonicalize().unwrap();
        let workspace = configuration_dir.join("workspace");
        let nodes = if self.distributed {
            let hosts = self.root_dir.join("hosts");
            let mut buf = String::new();
            File::open(hosts).unwrap().read_to_string(&mut buf).unwrap();
            // skip first as that is the node running the bencher
            buf.lines()
                .skip(1)
                .take(configuration.nodes)
                .map(|l| format!("ssh://{l}:8000"))
                .collect()
        } else {
            (0..configuration.nodes)
                .map(|i| format!("local://127.0.0.1:{}", 8000 + (i * 3)))
                .collect()
        };
        let (mut store, leader_address) = match &configuration.store_config {
            StoreConfig::Lskv(config) => {
                let store_config = LskvStore {
                    config: config.clone(),
                    nodes,
                    configuration_dir: configuration_dir.clone(),
                    workspace: workspace.clone(),
                    http_version: 2,
                    tmpfs: configuration.tmpfs,
                };
                let store = store_config.run(&self.root_dir);
                store_config.wait_for_ready().await;
                let leader_address = store_config.get_leader_address();
                (store, leader_address)
            }
            StoreConfig::Etcd(config) => {
                let store_config = EtcdStore {
                    config: config.clone(),
                    nodes,
                    configuration_dir: configuration_dir.clone(),
                    workspace: workspace.clone(),
                    tmpfs: configuration.tmpfs,
                };
                let store = store_config.run(&self.root_dir);
                store_config.wait_for_ready().await;
                let leader_address = store_config.get_leader_address(&self.root_dir);
                (store, leader_address)
            }
        };

        let load_path = configuration_dir
            .join("load.csv")
            .to_string_lossy()
            .into_owned();
        let results_path = configuration_dir
            .join("results.csv")
            .to_string_lossy()
            .into_owned();
        // create the file so it can be used to mount in docker
        File::create(&load_path).unwrap();
        File::create(&results_path).unwrap();

        let mut docker_runner =
            exp::docker_runner::Runner::new(configuration_dir.clone().into()).await;
        let load_command = configuration.to_load_command(&self.root_dir, &leader_address);
        let loader_name = "apj39-bencher-exp-loader".to_owned();
        debug!("Launching ycsb load container");
        docker_runner
            .add_container(&exp::docker_runner::ContainerConfig {
                image_name: "ghcr.io/jeffa5/lskv".to_owned(),
                image_tag: "bencher-latest".to_owned(),
                name: loader_name.clone(),
                command: Some(load_command),
                cpus: None,
                memory: None,
                capabilities: None,
                env: None,
                network: Some("host".to_owned()),
                network_subnet: None,
                ports: None,
                pull: true,
                tmpfs: vec![],
                volumes: vec![
                    (
                        configuration_dir
                            .join("workspace")
                            .to_string_lossy()
                            .into_owned(),
                        "/workspace".to_owned(),
                    ),
                    (load_path, "/results.csv".to_owned()),
                ],
            })
            .await;

        docker_runner
            .docker_client()
            .wait_container::<String>(&loader_name, None)
            .next()
            .await;

        let _ = docker_runner
            .docker_client()
            .remove_container(
                &loader_name,
                Some(bollard::container::RemoveContainerOptions {
                    force: true,
                    ..Default::default()
                }),
            )
            .await;

        debug!("Launching ycsb run container");
        let mut bench_command = configuration.to_command(&self.root_dir, &leader_address);
        bench_command.append(&mut vec![
            "--max-record-index".to_owned(),
            configuration.total.to_string(),
        ]);
        let bench_name = "apj39-bencher-exp-bencher".to_owned();
        docker_runner
            .add_container(&exp::docker_runner::ContainerConfig {
                image_name: "ghcr.io/jeffa5/lskv".to_owned(),
                image_tag: "bencher-latest".to_owned(),
                name: bench_name.clone(),
                command: Some(bench_command),
                cpus: None,
                memory: None,
                capabilities: None,
                env: None,
                network: Some("host".to_owned()),
                network_subnet: None,
                ports: None,
                pull: false,
                tmpfs: vec![],
                volumes: vec![
                    (
                        configuration_dir
                            .join("workspace")
                            .to_string_lossy()
                            .into_owned(),
                        "/workspace".to_owned(),
                    ),
                    (results_path, "/results.csv".to_owned()),
                ],
            })
            .await;

        docker_runner
            .docker_client()
            .wait_container::<String>(&bench_name, None)
            .next()
            .await;

        let _ = docker_runner
            .docker_client()
            .remove_container(
                &bench_name,
                Some(bollard::container::RemoveContainerOptions {
                    force: true,
                    ..Default::default()
                }),
            )
            .await;

        nix::sys::signal::kill(
            nix::unistd::Pid::from_raw(store.id() as i32),
            nix::sys::signal::Signal::SIGINT,
        )
        .expect("cannot send ctrl-c");
        let result = store.wait().unwrap();
        if result.success() {
            Ok(())
        } else {
            Err("Failed to run cluster".into())
        }
    }

    async fn post_run(&mut self, _configuration: &Self::Configuration) -> exp::ExpResult<()> {
        Ok(())
    }

    fn analyse(
        &mut self,
        experiment_dir: &Path,
        _environment: Environment,
        configurations: Vec<(Self::Configuration, PathBuf)>,
    ) {
        let all_results_file = experiment_dir.join("results.csv");
        println!("Merging results to {:?}", all_results_file);
        let mut all_data_opt = None;
        for (config, config_dir) in &configurations {
            let mut dummy_writer = Vec::new();
            {
                let mut config_header = csv::Writer::from_writer(&mut dummy_writer);
                config_header.serialize(config).unwrap();
            }
            let config_data = CsvReader::new(std::io::Cursor::new(dummy_writer))
                .has_header(true)
                .finish()
                .unwrap();

            let results_file = config_dir.join("results.csv");

            if results_file.is_file() {
                info!(?results_file, "Loading results");
                let mut schema = Schema::new();
                schema.with_column("member_id".into(), DataType::UInt64);
                let results_data = CsvReader::from_path(results_file)
                    .unwrap()
                    .has_header(true)
                    .with_dtypes(Some(Arc::new(schema)))
                    .finish()
                    .unwrap();

                let config_and_results_data =
                    config_data.cross_join(&results_data, None, None).unwrap();

                if let Some(all_data) = all_data_opt {
                    all_data_opt = Some(
                        diag_concat_lf([all_data, config_and_results_data.lazy()], true, true)
                            .unwrap(),
                    );
                } else {
                    all_data_opt = Some(config_and_results_data.lazy());
                }
            }
        }
        let mut csv_file = File::create(all_results_file).unwrap();
        if let Some(all_data) = all_data_opt {
            CsvWriter::new(&mut csv_file)
                .finish(&mut all_data.collect().unwrap())
                .unwrap();
        }
    }
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct Config {
    rate: u32,
    total: u32,
    max_clients: Option<u32>,
    workload: YcsbWorkload,
    nodes: usize,
    tmpfs: bool,
    #[serde(flatten)]
    store_config: StoreConfig,
}

impl exp::ExperimentConfiguration for Config {}

impl Config {
    fn to_command(&self, root_dir: &Path, leader_address: &str) -> Vec<String> {
        let mut cmd = vec![
            "bencher".to_owned(),
            "--write-endpoints".to_owned(),
            leader_address.to_owned(),
            "--read-endpoints".to_owned(),
            self.client_addresses(root_dir).join(","),
            "--common-dir".to_owned(),
            "/workspace/common".to_owned(),
            "--out-file".to_owned(),
            "/results.csv".to_owned(),
            "ycsb".to_owned(),
            "--rate".to_owned(),
            self.rate.to_string(),
            "--total".to_owned(),
            self.total.to_string(),
        ];
        if let Some(max_clients) = self.max_clients {
            cmd.append(["--max-clients".to_owned(), max_clients.to_string()]);
        }
        cmd.append(&mut self.workload.to_command());
        cmd
    }

    fn to_load_command(&self, root_dir: &Path, leader_address: &str) -> Vec<String> {
        vec![
            "bencher".to_owned(),
            "--write-endpoints".to_owned(),
            leader_address.to_owned(),
            "--read-endpoints".to_owned(),
            self.client_addresses(root_dir).join(","),
            "--common-dir".to_owned(),
            "/workspace/common".to_owned(),
            "--out-file".to_owned(),
            "/results.csv".to_owned(),
            "ycsb".to_owned(),
            "--rate".to_owned(),
            self.rate.to_string(),
            "--total".to_owned(),
            self.total.to_string(),
            "--insert-weight".to_owned(),
            "1".to_owned(),
        ]
    }

    fn client_addresses(&self, root_dir: &Path) -> Vec<String> {
        let hosts = root_dir.join("hosts");
        let buf = fs::read_to_string(hosts).unwrap();
        // skip first as that is the node running the bencher
        buf.lines()
            .skip(1)
            .take(self.nodes)
            .map(|l| format!("https://{l}:8000"))
            .collect()
    }
}

#[derive(Debug, Copy, Clone, serde::Serialize, serde::Deserialize)]
pub enum YcsbWorkload {
    A,
    B,
    C,
    D,
    E,
    F,
}

impl YcsbWorkload {
    fn to_command(&self) -> Vec<String> {
        let args = match self {
            Self::A => vec![
                "--read-weight",
                "1",
                "--update-weight",
                "1",
                "--request-distribution",
                "zipfian",
            ],
            Self::B => vec![
                "--read-weight",
                "95",
                "--update-weight",
                "5",
                "--request-distribution",
                "zipfian",
            ],
            Self::C => vec!["--read-weight", "1", "--request-distribution", "zipfian"],
            Self::D => vec![
                "--read-weight",
                "95",
                "--insert-weight",
                "5",
                "--request-distribution",
                "zipfian",
            ],
            Self::E => vec![
                "--scan-weight",
                "95",
                "--insert-weight",
                "5",
                "--max-scan-length",
                "100",
                "--request-distribution",
                "zipfian",
            ],
            Self::F => vec![
                "--read-weight",
                "1",
                "--rmw-weight",
                "1",
                "--request-distribution",
                "zipfian",
            ],
        };
        args.into_iter().map(|i| i.to_owned()).collect()
    }
}
