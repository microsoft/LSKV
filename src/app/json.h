#pragma once

#include "ccf/json_handler.h"
#include "etcd.pb.h"

namespace etcdserverpb
{

  using json = nlohmann::json;
  // Range
  void from_json(const json& j, RangeRequest& req);
  void to_json(json& j, const RangeResponse& res);
  // Put
  void from_json(const json& j, PutRequest& req);
  void to_json(json& j, const PutResponse& res);
  // DeleteRange
  void from_json(const json& j, DeleteRangeRequest& req);
  void to_json(json& j, const DeleteRangeResponse& res);
};