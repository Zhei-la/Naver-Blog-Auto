import cloudinary
import cloudinary.uploader
import cloudinary.api
import os

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def upload_image(file_data, filename):
    """이미지 Cloudinary에 업로드"""
    try:
        result = cloudinary.uploader.upload(
            file_data,
            folder="naver-blog-templates",
            public_id=filename,
            overwrite=True
        )
        return {"success": True, "url": result["secure_url"], "public_id": result["public_id"]}
    except Exception as e:
        return {"success": False, "message": str(e)}

def delete_image(public_id):
    """이미지 삭제"""
    try:
        cloudinary.uploader.destroy(public_id)
        return True
    except:
        return False

def render_template(template_body, variables):
    """템플릿 변수 치환
    {{키워드}}, {{지역}}, {{업체명}}, {{전화번호}}, {{주소}} 등
    """
    result = template_body
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result
