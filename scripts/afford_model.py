import os

import numpy as np
import torch
from PIL import Image
from torchvision import transforms


from models.multimodal_encoder.siglip_encoder import SiglipVisionTower
from models.multimodal_encoder.t5_encoder import T5Embedder
from models.multimodal_encoder.qwen25_encoder import Qwen2Embedder
from models.runner import DiTRunner


# Create the RDT model
def create_model(args, **kwargs):
    model = RoboticDiffusionTransformerModel(args, **kwargs)
    pretrained = kwargs.get("pretrained", None)
    if (
        pretrained is not None 
        and os.path.isfile(pretrained)
    ):
        model.load_pretrained_weights(pretrained)
        # print load pretrained model successful.')
    return model


class RoboticDiffusionTransformerModel(object):
    """A wrapper for the RDT model, which handles
            1. Model initialization
            2. Encodings of instructions
            3. Model inference
    """
    def __init__(
        self, args, 
        device='cuda',
        dtype=torch.bfloat16,
        image_size=None,
        control_frequency=25,
        pretrained=None,
        pretrained_vision_encoder_name_or_path=None,
        pretrained_text_encoder_name_or_path=None,
        text_encoder='Qwen2.5-7B'
    ):
        self.args = args
        self.dtype = dtype
        self.image_size = image_size
        self.device = device
        # self.control_frequency = control_frequency
        self.text_encoder_name = text_encoder
        # We do not use the text encoder due to limited GPU memory
        self.text_tokenizer, self.text_model = self.get_text_encoder(pretrained_text_encoder_name_or_path)
        self.image_processor, self.vision_model = self.get_vision_encoder(pretrained_vision_encoder_name_or_path)
        self.policy = self.get_policy(pretrained)
        
        self.reset()

    def get_policy(self, pretrained):
        """Initialize the model."""

        
        # Initialize model with arguments
        if (
            pretrained is None
            or os.path.isfile(pretrained)
        ):

            

            img_cond_len = (self.args["common"]["img_history_size"] 
                            * self.args["common"]["num_cameras"] 
                            * self.vision_model.num_patches)
            _model = DiTRunner(
                action_dim=self.args["common"]["state_dim"],
                pred_horizon=self.args["common"]["action_chunk_size"],
                config=self.args["model"],
                lang_token_dim=self.args["model"]["lang_token_dim"],
                img_token_dim=self.args["model"]["img_token_dim"],
                state_token_dim=self.args["model"]["state_token_dim"],
                max_lang_cond_len=self.args["dataset"]["tokenizer_max_length"],
                img_cond_len=img_cond_len,
                img_pos_embed_config=[
                    # No initial pos embed in the last grid size
                    # since we've already done in ViT
                    ("image", (self.args["common"]["img_history_size"], 
                        self.args["common"]["num_cameras"], 
                        -self.vision_model.num_patches)),  
                ],
                lang_pos_embed_config=[
                    # Similarly, no initial pos embed for language
                    ("lang", -self.args["dataset"]["tokenizer_max_length"]),
                ],
                dtype=self.dtype,
           
            )
        else:
            img_cond_len =             (self.args["common"]["img_history_size"] 
                * self.args["common"]["num_cameras"] 
                * self.vision_model.num_patches)
            #2187

           

            _model = DiTRunner.from_pretrained(pretrained,action_dim=self.args["common"]["state_dim"],
                                               pred_horizon=self.args["common"]["action_chunk_size"],
                                               config=self.args["model"],
                                               lang_token_dim=self.args["model"]["lang_token_dim"],
                                               state_token_dim=self.args["model"]["state_token_dim"],
                                                img_cond_len=img_cond_len,
                                                img_pos_embed_config=[
                                                    # No initial pos embed in the last grid size
                                                    # since we've already done in ViT
                                                    ("image", (self.args["common"]["img_history_size"], 
                                                        self.args["common"]["num_cameras"], 
                                                        -self.vision_model.num_patches)),  
                                                ],
                                                lang_pos_embed_config=[
                                                    # Similarly, no initial pos embed for language
                                                    ("lang", -self.args["dataset"]["tokenizer_max_length"]),
                                                ],
                                                dtype=self.dtype,
                                               )
            # _model = DiTRunner(
            #     action_dim=self.args["common"]["state_dim"],
            #     pred_horizon=self.args["common"]["action_chunk_size"],
            #     config=self.args["model"],
            #     lang_token_dim=self.args["model"]["lang_token_dim"],
            #     img_token_dim=self.args["model"]["img_token_dim"],
            #     state_token_dim=self.args["model"]["state_token_dim"],
            #     max_lang_cond_len=self.args["dataset"]["tokenizer_max_length"],
            #     img_cond_len=img_cond_len,
            #     img_pos_embed_config=[
            #         # No initial pos embed in the last grid size
            #         # since we've already done in ViT
            #         ("image", (self.args["common"]["img_history_size"], 
            #             self.args["common"]["num_cameras"], 
            #             -self.vision_model.num_patches)),  
            #     ],
            #     # None,
            #     lang_pos_embed_config=[
            #         # Similarly, no initial pos embed for language
            #         ("lang", -self.args["dataset"]["tokenizer_max_length"]),
            #     ],
            #     dtype=self.dtype,
           
            # )

            # state_dict = torch.load(os.path.join(pretrained,'pytorch_model.bin'), map_location="cpu")

            # filtered_state_dict = {k: v for k, v in state_dict.items() if k in _model.state_dict() and v.size() == _model.state_dict()[k].size()}

            # _model.load_state_dict(filtered_state_dict, strict=False)
            ##

        return _model

    def get_text_encoder(self, pretrained_text_encoder_name_or_path):
        if self.text_encoder_name=='Qwen2.5-7B':
            text_embedder = Qwen2Embedder(from_pretrained=pretrained_text_encoder_name_or_path, 
                            model_max_length=self.args["dataset"]["tokenizer_max_length"],
                            device=self.device)
        elif self.text_encoder_name=='t5-v1_1-xxl':
            text_embedder = T5Embedder(from_pretrained=pretrained_text_encoder_name_or_path, 
                                    model_max_length=self.args["dataset"]["tokenizer_max_length"], 
                                    device=self.device)

        tokenizer, text_encoder = text_embedder.tokenizer, text_embedder.model
        return tokenizer, text_encoder

    def get_vision_encoder(self, pretrained_vision_encoder_name_or_path):
        vision_encoder = SiglipVisionTower(vision_tower=pretrained_vision_encoder_name_or_path, args=None)
        image_processor = vision_encoder.image_processor
        return image_processor, vision_encoder

    def reset(self):
        """Set model to evaluation mode.
        """
        device = self.device
        weight_dtype = self.dtype
        self.policy.eval()
        # self.text_model.eval()
        self.vision_model.eval()

        self.policy = self.policy.to(device, dtype=weight_dtype)
        # self.text_model = self.text_model.to(device, dtype=weight_dtype)
        self.vision_model = self.vision_model.to(device, dtype=weight_dtype)

    def load_pretrained_weights(self, pretrained=None):
        if pretrained is None:
            return 
        print(f'Loading weights from {pretrained}')
        filename = os.path.basename(pretrained)
        if filename.endswith('.pt'):
            checkpoint =  torch.load(pretrained)
            self.policy.load_state_dict(checkpoint["module"])
        elif filename.endswith('.safetensors'):
            from safetensors.torch import load_model
            load_model(self.policy, pretrained)
        else:
            raise NotImplementedError(f"Unknown checkpoint format: {pretrained}")

    def encode_instruction(self, instruction, device="cuda"):
        """Encode string instruction to latent embeddings.

        Args:
            instruction: a string of instruction
            device: a string of device
        
        Returns:
            pred: a tensor of latent embeddings of shape (text_max_length, 512)
        """
        tokens = self.text_tokenizer(
            instruction, return_tensors="pt",
            padding="longest",
            truncation=True
        )["input_ids"].to(device)

        tokens = tokens.view(1, -1)
        with torch.no_grad():
            pred = self.text_model(tokens).last_hidden_state.detach()

        return pred


    @torch.no_grad()
    def step(self, images, text_embeds,poa=False):
        """
        Predict the next action chunk given the 
        proprioceptive states, images, and instruction embeddings.

        Args:
            proprio: proprioceptive states
            images: RGB images, the order should be
                [ext_{t-1}, right_wrist_{t-1}, left_wrist_{t-1}, 
                ext_{t}, right_wrist_{t}, left_wrist_{t}]
            text_embeds: instruction embeddings

        Returns:
            action: predicted action
        """
        device = self.device
        dtype = self.dtype
        
        # The background image used for padding
        background_color = np.array([
            int(x*255) for x in self.image_processor.image_mean
        ], dtype=np.uint8).reshape(1, 1, 3)
        background_image = np.ones((
            self.image_processor.size["height"], 
            self.image_processor.size["width"], 3), dtype=np.uint8
        ) * background_color
        
        # Preprocess the images by order and encode them
        image_tensor_list = []
        for image in images:
            if image is None:
                # Replace it with the background image
                image = Image.fromarray(background_image)
            
            if self.image_size is not None:
                image = transforms.Resize(self.data_args.image_size)(image)
            
            if self.args["dataset"].get("auto_adjust_image_brightness", False):
                pixel_values = list(image.getdata())
                average_brightness = sum(sum(pixel) for pixel in pixel_values) / (len(pixel_values) * 255.0 * 3)
                if average_brightness <= 0.15:
                    image = transforms.ColorJitter(brightness=(1.75,1.75))(image)
                    
            if self.args["dataset"].get("image_aspect_ratio", "pad") == 'pad':
                def expand2square(pil_img, background_color):
                    width, height = pil_img.size
                    if width == height:
                        return pil_img
                    elif width > height:
                        result = Image.new(pil_img.mode, (width, width), background_color)
                        result.paste(pil_img, (0, (width - height) // 2))
                        return result
                    else:
                        result = Image.new(pil_img.mode, (height, height), background_color)
                        result.paste(pil_img, ((height - width) // 2, 0))
                        return result
                image = expand2square(image, tuple(int(x*255) for x in self.image_processor.image_mean))
            # print('********* image shape',image.size)
            image = self.image_processor.preprocess(image, return_tensors='pt')['pixel_values'][0]
            image_tensor_list.append(image)

        image_tensor = torch.stack(image_tensor_list, dim=0).to(device, dtype=dtype)

        image_embeds = self.vision_model(image_tensor).detach()
        if poa:
            if self.args["common"]["img_history_size"]==2:
                image_diffs = image_embeds[1::2, :, :] - image_embeds[0::2, :, :]
                image_embeds[0::2, :, :] = image_diffs
                # print('-- use position offset attention --')

        image_embeds = image_embeds.reshape(-1, self.vision_model.hidden_size).unsqueeze(0)

        
        text_embeds = text_embeds.to(device, dtype=dtype)
        
        # Predict the next action chunk given the inputs
        trajectory = self.policy.predict_action(
            lang_tokens=text_embeds,
            lang_attn_mask=torch.ones(
                text_embeds.shape[:2], dtype=torch.bool,
                device=text_embeds.device),
            img_tokens=image_embeds,

        )

        return trajectory
