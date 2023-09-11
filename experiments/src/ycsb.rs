use crate::stores::lskv::LskvStore;
use exp::Environment;
use exp::Experiment;
use futures_util::StreamExt;
use std::fs::File;
use std::path::Path;
use std::path::PathBuf;

pub struct YcsbExperiment {
    pub root_dir: PathBuf,
}

#[async_trait::async_trait]
impl Experiment for YcsbExperiment {
    type Configuration = Config;

    fn configurations(&mut self) -> Vec<Self::Configuration> {
        let mut configs = Vec::new();
        let nodes = 1;
        for rate in [100, 500, 1000, 2000, 5000] {
            for workload in [
                YcsbWorkload::A,
                YcsbWorkload::B,
                YcsbWorkload::C,
                YcsbWorkload::D,
                YcsbWorkload::E,
            ] {
                let config = Config {
                    rate,
                    total: rate * 10,
                    workload,
                    nodes,
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
        let nodes = (0..configuration.nodes)
            .map(|i| format!("local://127.0.0.1:{}", 8000 + (i * 3)))
            .collect();
        let store_config = LskvStore {
            nodes,
            enclave: "virtual".to_owned(),
            worker_threads: 1,
            sig_tx_interval: 100,
            sig_ms_interval: 1,
            ledger_chunk_bytes: 1000,
            snapshot_tx_interval: 1000,
            configuration_dir: configuration_dir.clone(),
            workspace: workspace.clone(),
            http_version: 2,
            tmpfs: false,
        };
        let mut store = store_config.run(&self.root_dir);
        store_config.wait_for_ready().await;

        let results_path = configuration_dir
            .join("results.csv")
            .to_string_lossy()
            .into_owned();
        // create the file so it can be used to mount in docker
        File::create(&results_path).unwrap();

        let mut docker_runner =
            exp::docker_runner::Runner::new(configuration_dir.clone().into()).await;
        let command = configuration.to_command();
        let bench_name = "apj39-bencher-exp-bencher".to_owned();
        docker_runner
            .add_container(&exp::docker_runner::ContainerConfig {
                image_name: "ghcr.io/jeffa5/lskv".to_owned(),
                image_tag: "bencher-latest".to_owned(),
                name: bench_name.clone(),
                command: Some(command),
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
        _experiment_dir: &Path,
        _environment: Environment,
        _configurations: Vec<(Self::Configuration, PathBuf)>,
    ) {
        todo!()
    }
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct Config {
    rate: u32,
    total: u32,
    workload: YcsbWorkload,
    nodes: u32,
}

impl exp::ExperimentConfiguration for Config {}

impl Config {
    fn to_command(&self) -> Vec<String> {
        let mut cmd = vec![
            "bencher".to_owned(),
            "--endpoint".to_owned(),
            "https://127.0.0.1:8000".to_owned(),
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
        cmd.append(&mut self.workload.to_command());
        cmd
    }
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
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
            Self::F => todo!(),
        };
        args.into_iter().map(|i| i.to_owned()).collect()
    }
}
