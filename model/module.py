class PatchEmbedding(layers.Layer):
    def __init__(self, embed_dim, num_frame, patch_height, patch_width, **kwargs):
        super().__init__(**kwargs)
        self.projection = layers.Conv3D(
            filters=embed_dim,
            kernel_size=(num_frame, patch_height, patch_width), 
            strides=(num_frame, patch_height, patch_width), 
            padding="VALID",
        )
        self.flatten = layers.Reshape(target_shape=(-1, embed_dim))

    def call(self, videos):
        projected_patches = self.projection(videos)
        flattened_patches = self.flatten(projected_patches)
        return flattened_patches

class PositionalEncoding(tf.keras.layers.Layer):
    def __init__(self, sequence_length, embed_dim, **kwargs):
        super().__init__(**kwargs)
        self.positional_encoding = self.add_weight(
            "positional_encoding",
            shape=(1, sequence_length, embed_dim),
            initializer=tf.keras.initializers.RandomNormal(),
            trainable=True
        )
    
    def call(self, inputs):
        length = tf.shape(inputs)[1]
        return self.positional_encoding[:, :length, :]

class TransformerBlock(tf.keras.layers.Layer):
    def __init__(self, d_models, num_heads, **kwargs):
        super().__init__(**kwargs)
        d = d_models // num_heads
        self.attention = layers.MultiHeadAttention(num_heads=num_heads, key_dim=d, dropout=0.1)
        self.layernorm_1 = layers.LayerNormalization()
        self.layernorm_2 = layers.LayerNormalization()
        self.dense = layers.Dense(d_models, activation="gelu")
        self.densel = layers.Dense(d_models)

    def call(self, query, key, value, mask=None, training=True):
        attention_output = self.attention(query=query, key=key, value=value, attention_mask=mask, training=training)
        out_1 = self.layernorm_1(layers.Add()([query, attention_output]))
        inputs = self.densel(self.dense(out_1))
        out = self.layernorm_2(layers.Add()([inputs, out_1]))
        return out

class TransformerDecoderBlock(tf.keras.Model):
    def __init__(self, d_models, num_heads, vocab_size, seq_length, num_l, **kwargs):
        super().__init__(**kwargs)
        self.token_embeddings = layers.Embedding(input_dim=vocab_size, output_dim=d_models)
        self.embed_scale = tf.math.sqrt(tf.cast(d_models, tf.float32))
        self.positional_encoding = PositionalEncoding(sequence_length=seq_length, embed_dim=d_models)
        self.mask_att = layers.MultiHeadAttention(
            num_heads=num_heads, key_dim=d_models // num_heads, dropout=0.1
        )
        self.layernorm = layers.LayerNormalization()
        self.attention = [TransformerBlock(d_models, num_heads) for _ in range(num_l)]
        self.linear = layers.Dense(d_models,)
        self.out = layers.Dense(vocab_size)
    
    def call(self, inp, training=True):
        inputs, en_out, mask = inp
        inputs = self.token_embeddings(inputs)
        inputs = layers.Add()([inputs * self.embed_scale, self.positional_encoding(inputs)])
        causal_mask = self.get_causal_attention_mask(inputs)
        if mask is not None:
            padding_mask = tf.cast(mask[:, :, tf.newaxis], dtype=tf.int32)
            combined_mask = tf.cast(mask[:, tf.newaxis, :], dtype=tf.int32)
            combined_mask = tf.minimum(combined_mask, causal_mask)
        mask_out = self.mask_att(
            query=inputs, key=inputs, value=inputs, attention_mask=combined_mask, training=training
        )
        inputs = self.layernorm(layers.Add()([inputs, mask_out]))
        for layer in self.attention:
            inputs = layer(query=inputs, key=en_out, value=en_out, mask=padding_mask, training=training)
        return self.out(self.linear(inputs))

    def get_causal_attention_mask(self, inputs):
        input_shape = tf.shape(inputs)
        batch_size, sequence_length = input_shape[0], input_shape[1]
        i = tf.range(sequence_length)[:, tf.newaxis]
        j = tf.range(sequence_length)
        mask = tf.cast(i >= j, dtype="int32")
        mask = tf.reshape(mask, (1, input_shape[1], input_shape[1]))
        mult = tf.concat(
            [tf.expand_dims(batch_size, -1), tf.constant([1, 1], dtype=tf.int32)],
            axis=0,
        )
        return tf.tile(mask, mult)
