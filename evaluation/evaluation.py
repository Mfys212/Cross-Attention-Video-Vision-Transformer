class EvalMetrics():
    def __init__(self, model, vectorization, SEQ_LENGTH, valid_data, FRAMES_STORAGE_PATH):
        self.model = model
        self.vectorization = vectorization
        self.vocab = vectorization.get_vocabulary()
        self.index_lookup = dict(zip(range(len(self.vocab)), self.vocab))
        self.max_decoded_sentence_length = SEQ_LENGTH - 1
        self.valid_videos = list(valid_data.keys())
        self.FRAMES_STORAGE_PATH = FRAMES_STORAGE_PATH
        self.valid_data = valid_data

    def generate_caption(self, video_path):
        if video_path is None:
            sample_video = np.random.choice(self.valid_videos)
        else:
            sample_video = video_path
            
        video_name = os.path.splitext(os.path.basename(sample_video))[0]
        video_storage_path = os.path.join(self.FRAMES_STORAGE_PATH, video_name)
        if not os.path.exists(video_storage_path) or len(os.listdir(video_storage_path)) == 0:
            save_video_frames(sample_video, video_storage_path)
        video_frames = tf_load_frames_from_directory(video_storage_path)
        video_frames = tf.expand_dims(video_frames, axis=0) 
        encoded_frames = self.model.encoder(video_frames)
        decoded_caption = "<start>"
        
        for i in range(self.max_decoded_sentence_length):
            tokenized_caption = self.vectorization([decoded_caption])[:, :-1]
            mask = tf.math.not_equal(tokenized_caption, 0)
            predictions = self.model.decoder([tokenized_caption, encoded_frames, mask])
            sampled_token_index = np.argmax(predictions[0, i, :])
            sampled_token = self.index_lookup[sampled_token_index]
            if sampled_token == "<end>":
                break
            decoded_caption += " " + sampled_token
            
        decoded_caption = decoded_caption.replace("<start> ", "")
        decoded_caption = decoded_caption.replace(" <end>", "").strip()
        return decoded_caption

    def acc_loss():
        acc, loss = self.model.evaluate(self.valid_data, verbose=0)
        return acc, loss

    def compute_cider():
        references, hypotheses, val = {}, {}, {}
        val = {
            key: [text.replace("<start> ", "").replace(" <end>", "") for text in value]
            for key, value in self.valid_data.items()
        }
    
        for video_path, reference_captions in tqdm(val.items(), desc="Compute Score"):
            generated_caption = self.generate_caption(video_path)
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            references[video_name] = reference_captions
            hypotheses[video_name] = [generated_caption]
    
        cider_scorer = Cider()
        score, _ = cider_scorer.compute_score(references, hypotheses)
        return score
