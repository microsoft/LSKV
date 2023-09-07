use std::path::Path;

use crate::protos::etcdserverpb::kv_client::KvClient;
use crate::protos::etcdserverpb::PutRequest;
use crate::protos::etcdserverpb::RangeRequest;
use async_trait::async_trait;
use loadbench::client::{Dispatcher, DispatcherGenerator};
use loadbench::input::InputGenerator;
use rand::{distributions::Alphanumeric, rngs::StdRng, Rng};
use rand_distr::{Distribution, WeightedAliasIndex, Zipf};
use tonic::transport::{Certificate, Channel, ClientTlsConfig, Identity};

/// Generate inputs for the YCSB workloads.
pub struct YcsbInputGenerator {
    pub read_weight: u32,
    pub scan_weight: u32,
    pub insert_weight: u32,
    pub update_weight: u32,
    pub read_all_fields: bool,
    pub fields_per_record: u32,
    pub field_value_length: usize,
    pub operation_rng: StdRng,
    pub max_record_index: u32,
    pub request_distribution: RequestDistribution,
}

#[derive(Debug, Clone, Copy, clap::ValueEnum)]
pub enum RequestDistribution {
    /// Uniformly over the existing keys.
    Uniform,
    /// Weighted toward one end.
    Zipfian,
    /// The last one available.
    Latest,
}

impl YcsbInputGenerator {
    pub fn new_record_key(&mut self) -> String {
        // TODO: may not want incremental inserts
        self.max_record_index += 1;
        format!("user{:08}", self.max_record_index)
    }

    pub fn existing_record_key(&mut self) -> String {
        let index = match self.request_distribution {
            RequestDistribution::Zipfian => {
                let s: f64 = self
                    .operation_rng
                    .sample(Zipf::new(self.max_record_index as u64, 1.5).unwrap());
                s.floor() as u32
            }
            RequestDistribution::Uniform => self.operation_rng.gen_range(0..=self.max_record_index),
            RequestDistribution::Latest => self.max_record_index,
        };
        format!("user{:08}", index)
    }

    pub fn field_key(i: u32) -> String {
        format!("field{i}")
    }

    pub fn field_value(&mut self) -> String {
        (&mut self.operation_rng)
            .sample_iter(&Alphanumeric)
            .take(self.field_value_length)
            .map(char::from)
            .collect()
    }
}

#[derive(Debug)]
pub enum YcsbInput {
    /// Insert a new record.
    Insert {
        record_key: String,
        fields: Vec<(String, String)>,
    },
    /// Update a record by replacing the value of one field.
    Update {
        record_key: String,
        field_key: String,
        field_value: String,
    },
    /// Read a single, randomly chosen field from the record.
    ReadSingle {
        record_key: String,
        field_key: String,
    },
    /// Read all fields from a record.
    ReadAll { record_key: String },
    /// Scan records in order, starting at a randomly chosen key
    Scan { start_key: String, scan_length: u32 },
}

impl InputGenerator for YcsbInputGenerator {
    type Input = YcsbInput;

    fn close(self) {}

    fn next(&mut self) -> Option<Self::Input> {
        let weights = [
            self.read_weight,
            self.scan_weight,
            self.insert_weight,
            self.update_weight,
        ];
        let dist = WeightedAliasIndex::new(weights.to_vec()).unwrap();
        let weight_index = dist.sample(&mut self.operation_rng);
        let input = match weight_index {
            // read single
            0 => YcsbInput::ReadSingle {
                record_key: self.existing_record_key(),
                field_key: "field0".to_owned(),
            },
            // read all
            1 => YcsbInput::ReadAll {
                record_key: self.existing_record_key(),
            },
            // insert
            2 => YcsbInput::Insert {
                record_key: self.new_record_key(),
                fields: (0..self.fields_per_record)
                    .into_iter()
                    .map(|i| (Self::field_key(i), self.field_value()))
                    .collect(),
            },
            // update
            3 => YcsbInput::Update {
                record_key: self.existing_record_key(),
                field_key: "field0".to_owned(),
                field_value: random_string(self.field_value_length),
            },
            i => {
                println!("got weight index {i}, but there was no input type to match");
                return None;
            }
        };
        // println!("generated ycsb input {:?}", input);
        Some(input)
    }
}

fn random_string(len: usize) -> String {
    let s: String = rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(len)
        .map(char::from)
        .collect();
    s
}

pub struct YcsbDispatcherGenerator {
    etcd_client: KvClient<Channel>,
}

impl YcsbDispatcherGenerator {
    pub async fn new(endpoint: String, common_dir: &Path) -> Self {
        let server_root_ca_cert =
            std::fs::read_to_string(common_dir.join("service_cert.pem")).unwrap();
        let server_root_ca_cert = Certificate::from_pem(server_root_ca_cert);
        let client_cert = std::fs::read_to_string(common_dir.join("user0_cert.pem")).unwrap();
        let client_key = std::fs::read_to_string(common_dir.join("user0_privk.pem")).unwrap();
        let client_identity = Identity::from_pem(client_cert, client_key);

        let tls = ClientTlsConfig::new()
            .ca_certificate(server_root_ca_cert)
            .identity(client_identity);

        let channel = Channel::from_shared(endpoint)
            .unwrap()
            .tls_config(tls)
            .unwrap()
            .connect()
            .await
            .unwrap();

        let client = KvClient::new(channel);
        Self {
            etcd_client: client,
        }
    }
}

impl DispatcherGenerator for YcsbDispatcherGenerator {
    type Dispatcher = YcsbDispatcher;

    fn generate(&mut self) -> Self::Dispatcher {
        YcsbDispatcher {
            etcd_client: self.etcd_client.clone(),
        }
    }
}

pub struct YcsbDispatcher {
    etcd_client: KvClient<Channel>,
}

#[async_trait]
impl Dispatcher for YcsbDispatcher {
    type Input = YcsbInput;

    type Output = ();

    async fn execute(&mut self, request: Self::Input) -> Result<Self::Output, String> {
        match request {
            YcsbInput::Insert { record_key, fields } => {
                for (field_key, field_value) in fields {
                    self.etcd_client
                        .put(PutRequest {
                            key: format!("{record_key}/{field_key}").into(),
                            value: field_value.into(),
                            ignore_lease: false,
                            ignore_value: false,
                            lease: 0,
                            prev_kv: false,
                        })
                        .await
                        .unwrap();
                }
            }
            YcsbInput::Update {
                record_key,
                field_key,
                field_value,
            } => {
                self.etcd_client
                    .put(PutRequest {
                        key: format!("{record_key}/{field_key}").into(),
                        value: field_value.into(),
                        ignore_lease: false,
                        ignore_value: false,
                        lease: 0,
                        prev_kv: false,
                    })
                    .await
                    .unwrap();
            }
            YcsbInput::ReadSingle {
                record_key,
                field_key,
            } => {
                self.etcd_client
                    .range(RangeRequest {
                        key: format!("{record_key}/{field_key}").into(),
                        range_end: vec![],
                        serializable: true,
                        revision: 0,
                        limit: 0,
                        max_create_revision: 0,
                        max_mod_revision: 0,
                        min_create_revision: 0,
                        min_mod_revision: 0,
                        keys_only: false,
                        count_only: false,
                        sort_order: 0,
                        sort_target: 0,
                    })
                    .await
                    .unwrap();
            }
            YcsbInput::ReadAll { record_key } => {
                self.etcd_client
                    .range(RangeRequest {
                        key: format!("{record_key}/").into(),
                        range_end: format!("{record_key}0").into(),
                        serializable: true,
                        revision: 0,
                        limit: 0,
                        max_create_revision: 0,
                        max_mod_revision: 0,
                        min_create_revision: 0,
                        min_mod_revision: 0,
                        keys_only: false,
                        count_only: false,
                        sort_order: 0,
                        sort_target: 0,
                    })
                    .await
                    .unwrap();
            }
            YcsbInput::Scan {
                start_key,
                scan_length,
            } => {
                // TODO
            }
        }
        Ok(())
    }
}

#[derive(Debug, clap::Args)]
pub struct Args {
    #[clap(long, default_value = "100")]
    pub rate: u64,
    #[clap(long, default_value = "1000")]
    pub total: u64,

    #[clap(long, default_value = "0")]
    pub initial_clients: u64,
    #[clap(long)]
    pub max_clients: Option<u32>,
    #[clap(long, default_value = "1")]
    pub read_weight: u32,
    #[clap(long, default_value = "1")]
    pub scan_weight: u32,
    #[clap(long, default_value = "1")]
    pub insert_weight: u32,
    #[clap(long, default_value = "1")]
    pub update_weight: u32,
    #[clap(long)]
    pub read_all_fields: bool,
    #[clap(long, default_value = "1")]
    pub fields_per_record: u32,
    #[clap(long, default_value = "1")]
    pub field_value_length: usize,
    #[clap(long, default_value = "1")]
    pub max_record_index: u32,
    #[clap(long, default_value = "uniform")]
    pub request_distribution: RequestDistribution,
}
