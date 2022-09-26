#include "json.h"

#include "etcd.pb.h"
#include "nlohmann/json.hpp"

namespace app::json
{
  etcdserverpb::RangeRequest RangeRequest::to_grpc() const
  {
    etcdserverpb::RangeRequest req;
    req.set_key(key);
    req.set_range_end(range_end);
    return req;
  }
} // namespace app::json

namespace etcdserverpb
{
  using json = nlohmann::json;
  void from_json(const json& j, RangeRequest& req)
  {
    j.at("key").get_to(*req.mutable_key());
    j.at("range_end").get_to(*req.mutable_range_end());

    int64_t limit;
    j.at("limit").get_to(limit);
    req.set_limit(limit);

    int64_t revision;
    j.at("revision").get_to(revision);
    req.set_revision(revision);

    bool serializable;
    j.at("serializable").get_to(serializable);
    req.set_serializable(serializable);

    // sort_order
    // sort_target

    bool keys_only;
    j.at("keys_only").get_to(keys_only);
    req.set_keys_only(keys_only);

    bool count_only;
    j.at("count_only").get_to(count_only);
    req.set_count_only(count_only);

    int64_t min_mod_revision;
    j.at("min_mod_revision").get_to(min_mod_revision);
    req.set_min_mod_revision(min_mod_revision);

    int64_t max_mod_revision;
    j.at("max_mod_revision").get_to(max_mod_revision);
    req.set_max_mod_revision(max_mod_revision);

    int64_t min_create_revision;
    j.at("min_create_revision").get_to(min_create_revision);
    req.set_min_create_revision(min_create_revision);

    int64_t max_create_revision;
    j.at("max_create_revision").get_to(max_create_revision);
    req.set_max_create_revision(max_create_revision);
  }

  void to_json(json& j, const RangeResponse& req)
  {
    j = json{};
    auto kvs = json::array();
    for (const auto& kv : req.kvs())
    {
      json jkv = json{};
      jkv["key"] = kv.key();
      jkv["create_revision"] = kv.create_revision();
      jkv["mod_revision"] = kv.mod_revision();
      jkv["version"] = kv.version();
      jkv["value"] = kv.value();
      jkv["lease"] = kv.lease();
      kvs.push_back(jkv);
    }
    j["kvs"] = kvs;

    j["more"] = false;
    j["count"] = req.count();
  }
}