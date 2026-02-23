<!DOCTYPE html>
<html>
<head>
    <title>Handwriting to Text Converter</title>
    <script src="https://cdn.jsdelivr.net/npm/tesseract.js@4/dist/tesseract.min.js"></script>
    <style>
        body {
            font-family: Arial;
            text-align: center;
            margin: 40px;
        }
        textarea {
            width: 80%;
            height: 150px;
            margin-top: 20px;
        }
        button {
            padding: 10px 20px;
            margin-top: 10px;
            cursor: pointer;
        }
        img {
            max-width: 300px;
            margin-top: 20px;
        }
    </style>
</head>
<body>

    <h1>Handwritten Image to Text</h1>

    <input type="file" id="imageInput" accept="image/*">
    <br>
    <img id="preview">
    <br>

    <button onclick="convertImage()">Convert to Text</button>

    <h3>Extracted Text:</h3>
    <textarea id="outputText" placeholder="Your text will appear here..."></textarea>
    <br>
    <button onclick="copyText()">Copy Text</button>

<script>
const imageInput = document.getElementById('imageInput');
const preview = document.getElementById('preview');

imageInput.addEventListener('change', function() {
    const file = this.files[0];
    const reader = new FileReader();
    reader.onload = function(e) {
        preview.src = e.target.result;
    }
    reader.readAsDataURL(file);
});

function convertImage() {
    const image = preview.src;

    if (!image) {
        alert("Please upload an image first!");
        return;
    }

    Tesseract.recognize(
        image,
        'eng',
        { logger: m => console.log(m) }
    ).then(({ data: { text } }) => {
        document.getElementById("outputText").value = text;
    });
}

function copyText() {
    const textArea = document.getElementById("outputText");
    textArea.select();
    document.execCommand("copy");
    alert("Text copied!");
}
</script>

</body>
</html>