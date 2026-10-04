# WeSpeaker speaker-identity model

HaizFlow bundles the ONNX VoxCeleb ResNet34 speaker-identification
checkpoint published by the WeSpeaker project. It runs on CPU to assign speech
segments to approximate speaker identities; it does not clone a source voice.

- Publisher: WeSpeaker / wenet-e2e.
- Model repository: https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34
- Pinned revision: `ff1ac5bca8ef11e90662b879aa923979e0bd277b`.
- Upstream filename: `voxceleb_resnet34.onnx`.
- SHA-256: `9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1`.
- License declared by the publisher at this revision: Apache License 2.0.
- License text: [Apache-2.0.txt](Apache-2.0.txt).

The application stores the file under `wespeaker_en_voxceleb_resnet34.onnx`; the
checkpoint bytes are unchanged. HaizFlow's application license does not replace
the model's independent license. Retain this notice and the upstream license
when distributing the application or a resource pack containing this model.
