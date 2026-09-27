"""Local-only pharmacist prototype. No uploaded images or patient data persisted."""
import io,json,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
CATALOG=json.loads((Path(__file__).resolve().parents[1]/'data/medicine/catalog.json').read_text())
CLASS_NAMES=json.loads((Path(__file__).resolve().parents[1]/'data/medicine/class_names.json').read_text())
if set(CLASS_NAMES) != {m['id'] for m in CATALOG}:
    raise RuntimeError('Catalog and training class names differ.')
MODEL=None
LOCK=threading.Lock()
class InvalidImage(ValueError):
    pass

def predict(raw):
    global MODEL
    import numpy as np
    import tensorflow as tf
    from PIL import Image,ImageOps,UnidentifiedImageError
    Image.MAX_IMAGE_PIXELS=16000000
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width*im.height>16000000: raise InvalidImage('Image exceeds 16 megapixels. Resize and retry.')
            rgb=np.asarray(ImageOps.exif_transpose(im).convert('RGB'),dtype=np.float32)
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc: raise InvalidImage('Invalid or unsupported image.') from exc
    # Same RGB, bilinear 224x224, [-1,1] preprocessing as training notebook.
    x=tf.image.resize(rgb,(224,224),method='bilinear')
    x=tf.keras.applications.mobilenet.preprocess_input(x)[None,...]
    with LOCK:
        if MODEL is None:
            MODEL=tf.keras.models.load_model(ROOT/'NLM20_Visual_Verification/models/MobileNetV1_Frozen.keras',compile=False)
            if MODEL.output_shape[-1]!=len(CLASS_NAMES):raise RuntimeError('Model/class mapping mismatch.')
        scores=np.asarray(MODEL(x,training=False))[0]
    return {'candidates':[{'id':CLASS_NAMES[int(i)],'score':float(scores[i])} for i in np.argsort(scores)[-3:][::-1]],'verified':False}

from fastapi import APIRouter, Request, HTTPException
from starlette.concurrency import run_in_threadpool
router=APIRouter(tags=['medicine'])
@router.get('/medicine/catalog')
def catalog():
    return CATALOG
@router.post('/medicine/predict')
async def recognize(request: Request):
    if request.headers.get('content-type','').split(';')[0] not in ('image/jpeg','image/png','image/webp'):
        raise HTTPException(415, 'Use JPG, PNG or WebP.')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>10*1024*1024: raise HTTPException(413, 'Choose an image up to 10 MB.')
    if not raw: raise HTTPException(400, 'The image is empty.')
    try:
        return await run_in_threadpool(predict, bytes(raw))
    except InvalidImage as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        import logging
        logging.getLogger('madad.medicine').exception('Recognition failed')
        raise HTTPException(503, 'Image recognition is unavailable. Check the vision dependencies and model file.') from exc
