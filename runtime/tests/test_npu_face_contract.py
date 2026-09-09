import pytest
from pydantic import ValidationError
from ai_runtime.app.model.contracts import DeployModelRequest
from edge_agent.app.command.deployed_models import DeployedModel


def value():
 return {'modelVersionId':131,'artifactRelativePath':'models/131/model.zip','artifactPath':'/tmp/model.zip',
         'artifactFormat':'ARCHIVE','trustedArtifact':False,'sha256':'a'*64,'device':'RKNPU',
         'runtimeManifest':{'schemaVersion':'1.0','taskType':'FACE_VERIFICATION','preprocess':{'dtype':'UINT8','layout':'NHWC','scale':1},'decoder':{'type':'FACE_PAIR_SFACE_RKNN'}}}


def test_npu_pair_survives_registry_roundtrip():
 data=value();assert DeployModelRequest.model_validate(data).device=='RKNPU'
 saved=DeployedModel.model_validate(data).model_dump(by_alias=True)
 assert DeployedModel.model_validate(saved).device=='RKNPU'


@pytest.mark.parametrize('device,decoder',[('CPU','FACE_PAIR_SFACE_RKNN'),('RKNPU','FACE_PAIR_SFACE')])
def test_device_disagreement_is_not_silent_cpu_fallback(device,decoder):
 data=value();data['device']=device;data['runtimeManifest']['decoder']['type']=decoder
 with pytest.raises(ValidationError):DeployModelRequest.model_validate(data)
 with pytest.raises(ValidationError):DeployedModel.model_validate(data)
