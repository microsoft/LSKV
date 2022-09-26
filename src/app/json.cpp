// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "json.h"

#include "nlohmann/json.hpp"

#define CONTAINS_THEN_SET(ty, var) \
  if (j.contains(#var)) \
  { \
    ty v; \
    j.at(#var).get_to(v); \
    req.set_##var(v); \
  }

namespace etcdserverpb
{
  using json = nlohmann::json;

  void from_json(const json& j, RangeRequest& req)
  {
    j.at("key").get_to(*req.mutable_key());
    if (j.contains("range_end"))
    {
      j.at("range_end").get_to(*req.mutable_range_end());
    }

    CONTAINS_THEN_SET(int64_t, limit);
    CONTAINS_THEN_SET(int64_t, revision);
    CONTAINS_THEN_SET(bool, serializable);
    CONTAINS_THEN_SET(bool, keys_only);
    CONTAINS_THEN_SET(bool, count_only);
    CONTAINS_THEN_SET(int64_t, min_mod_revision);
    CONTAINS_THEN_SET(int64_t, max_mod_revision);
    CONTAINS_THEN_SET(int64_t, min_create_revision);
    CONTAINS_THEN_SET(int64_t, max_create_revision);

    // sort_order
    // sort_target
  }

  void to_json(json& j, const KeyValue& kv)
  {
    j["key"] = kv.key();
    j["create_revision"] = kv.create_revision();
    j["mod_revision"] = kv.mod_revision();
    j["version"] = kv.version();
    j["value"] = kv.value();
    j["lease"] = kv.lease();
  }

  void to_json(json& j, const RangeResponse& res)
  {
    auto kvs = json::array();
    for (const auto& kv : res.kvs())
    {
      json jkv = json{};
      to_json(jkv, kv);
      kvs.push_back(jkv);
    }
    j["kvs"] = kvs;
    j["more"] = false;
    j["count"] = res.count();
  }

  void from_json(const json& j, PutRequest& req)
  {
    j.at("key").get_to(*req.mutable_key());
    j.at("value").get_to(*req.mutable_value());

    CONTAINS_THEN_SET(int64_t, lease);
    CONTAINS_THEN_SET(bool, prev_kv);
    CONTAINS_THEN_SET(bool, ignore_value);
    CONTAINS_THEN_SET(bool, ignore_lease);
  }

  void to_json(json& j, const PutResponse& res)
  {
    json jkv = json{};
    to_json(jkv, res.prev_kv());
    j["prev_kv"] = jkv;
  }

  void from_json(const json& j, DeleteRangeRequest& req)
  {
    j.at("key").get_to(*req.mutable_key());

    if (j.contains("range_end"))
    {
      j.at("range_end").get_to(*req.mutable_range_end());
    }

    CONTAINS_THEN_SET(bool, prev_kv);
  }

  void to_json(json& j, const DeleteRangeResponse& res)
  {
    j["deleted"] = res.deleted();

    auto kvs = json::array();
    for (const auto& kv : res.prev_kvs())
    {
      json jkv = json{};
      to_json(jkv, kv);
      kvs.push_back(jkv);
    }
    j["prev_kvs"] = kvs;
  }
};
