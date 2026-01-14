
from typing import List,Union,Dict,Any

ResourceTypes = ['图片','视频','文档','音频','3D','其他']
AssetTypes = ['资产','资产文件','专题库']

def get_asset_type_text(asset_type):
    return AssetTypes[int(asset_type)-1]

def get_asset_type_id(asset_type):
    if not asset_type in AssetTypes:
        return 0
    return AssetTypes.index(asset_type)+1

def get_resource_type_text(resource_type):
    return ResourceTypes[int(resource_type)-1]

def get_resource_type_id(resource_type):
    if not resource_type in ResourceTypes:
        return 0
    return ResourceTypes.index(resource_type)+1

def prepare_search_params(recommend_types):
    if "None" in recommend_types:
        return 0
    if "专题库" in recommend_types:
        return 2
    if '资产' in recommend_types:
        return 1
    return 3
    
def prepare_recommend_params(recommend_types):
    if "专题库" in recommend_types:
        return ''
    if '资产' in recommend_types:
        return ''
    return ",".join([str(get_resource_type_id(i)) for i in recommend_types])

def conver_library_item_to_doc(file:LibraryItem):
    doc = '' 
    fid=f"专题库ID为：{file.library_id}，"
    # f_type=f"专题库类型为：{resource_type[int(file.resource_type)-1]}，"
    f_name=f"专题库名称为：{file.library_name}，"
    doc += f"{fid}{f_name}\n"
    return doc

def conver_library_items_to_doc(file_list:List[LibraryItem]):
    doc = '' 
    index =1
    for file in file_list:
        f_doc = conver_library_item_to_doc(file)
        doc += f"{index}、{f_doc}"
        index+=1
    return doc

def conver_resource_item_to_doc(file:ResourceItem):
    doc = '' 
    fid=f"数字资产ID为：{file.resource_id}，"
    f_type=f"数字资产类型为：{get_resource_type_text(file.resource_type)}，"
    f_name=f"数字资产名称为：{file.resource_name}，"
    # f_url=f"数字资产封面地址为：{file.image}"
    doc += f"{fid}{f_type}{f_name}\n"
    return doc


def conver_resource_items_to_doc(file_list:List[ResourceItem]):
    doc = '' 
    index =1
    for file in file_list:
        f_doc = conver_resource_item_to_doc(file)
        doc += f"{index}、{f_doc}"
        index+=1
    return doc

def conver_file_item_to_doc(file:FileItem):
    doc = '' 
    fid=f"文件ID为：{file.resource_file_id}，"
    f_type=f"文件类型为：{get_resource_type_text(file.resource_type)}，"
    f_name=f"文件名为：{file.file_name}，"
    f_content=f"文件内容为：{file.content} {file.content_fields}，"
    f_url=f"文件链接地址为：{file.view_url}，"
    rid=f"文件所属资产的ID为：{file.resource_id}"
    doc += f"{fid}{f_type}{f_name}{f_content}{f_url}{rid}\n"
    return doc

def conver_file_items_to_doc(file_list:List[FileItem]):
    doc = '' 
    index =1
    for file in file_list:
        f_doc = conver_file_item_to_doc(file)
        doc += f"{index}、{f_doc}"
        index+=1
    return doc

def conver_api_search_to_doc(api_search_result:APISearchResultData):
    knowledge_text=''
    if api_search_result and len(api_search_result.resource_list):
        knowledge_text +="\n数字资产列表如下：\n"
        knowledge_text += conver_resource_items_to_doc(api_search_result.resource_list)
        
    if api_search_result and len(api_search_result.resource_file_list):
        knowledge_text +="\n文件列表如下：\n"
        knowledge_text += conver_file_items_to_doc(api_search_result.resource_file_list)
    
    if api_search_result and len(api_search_result.library_list):
        knowledge_text +="\n专题库列表如下：\n"
        knowledge_text += conver_library_items_to_doc(api_search_result.library_list)
        
    return knowledge_text

def conver_recommend_file_item_to_doc(file:FileItem):
    doc = '' 
    fid=f"文件ID：{file.resource_file_id}，"
    f_type=f"文件类型：{get_resource_type_text(file.resource_type)}，"
    f_name=f"文件名：{file.file_name}，"
    f_content=f"文件内容：{file.content_fields}，"  #{file.content} 
    # f_url=f"文件URL：{file.view_url}，"
    # page_url=f"页面URL：http://192.168.10.198:9980/gzcvpanel/#/digitalAssetManagement/detailImage?assetFileId={file.resource_file_id}&assetFileIds={file.resource_file_id}，"
    # pic_url=f"链接URL：[![{file.file_name}]({file.view_url})]({file.view_url}?resource_file_id={file.resource_file_id}&resource_id={file.resource_id})，"
    rid=f"文件所属资产的ID：{file.resource_id}"
    doc += f"{f_name}{f_type}{f_content}\n"
    return doc

def conver_recommend_file_items_to_doc(file_list:List[FileItem]):
    doc = '' 
    index =1
    for file in file_list:
        f_doc = conver_recommend_file_item_to_doc(file)
        doc += f"{index}、{f_doc}"
        index+=1
    return doc

def conver_recommend_to_doc(input_query,api_search_result:APISearchResultData):
    knowledge_text=''
    has_result = False
    if api_search_result and len(api_search_result.library_list):
        knowledge_text +=f"与{input_query}相关的专题库列表如下：\n"
        knowledge_text += conver_library_items_to_doc(api_search_result.library_list)
        has_result = True
    else:
        knowledge_text +=f"没有找到与{input_query}相关的专题库\n"
        
    if api_search_result and len(api_search_result.resource_list):
        knowledge_text +=f"与{input_query}相关的数字资产列表如下：\n"
        knowledge_text += conver_resource_items_to_doc(api_search_result.resource_list)
        has_result = True
    else:
        knowledge_text +=f"没有找到与{input_query}相关的数字资产\n"
        
    if api_search_result and len(api_search_result.resource_file_list):
        knowledge_text +=f"与{input_query}相关的文件列表如下：\n"
        knowledge_text += conver_recommend_file_items_to_doc(api_search_result.resource_file_list)
        has_result = True
    else:
        knowledge_text +=f"没有找到与{input_query}相关的文件\n"
    
    if not has_result:
        knowledge_text +=f"因为没有找到任何相关的资源，所以没有可以推荐的内容.\n"
            
    return knowledge_text,has_result


#region  资产详情页面转文档
def convert_baseinfo_doc(baseInfo:dict):
    info ='当前页面的基本信息如下：\n'
    for k,v in baseInfo.items():
        if k=='id':
            info+='页面'
        info=info+ k +":" + str(v) +'，'
    info = info[:-1] + '。'
    return info


async def convert_resourcefilelist_doc(query:str,resources:list,rerank_model,ranker_filter):
    info ='\n当前页面为资产详情页，包含的资源文件列表如下：\n'
    array = []
    for i, res in enumerate(resources):
        res_info=''
        for k,v in res.items():
            res_info += str(k) +":"+ str(v) +'，'
        res_info = res_info[:-1] + '。 \n'
        array.append(res_info)
    scores = await rerank_model([[query,doc] for doc in array])
    docs = ranker_filter(array,scores,re_sort=True,threshold=-100)
    
    for i, res in enumerate(docs):
        res_info = f"{i+1}、{res}"
        info += res_info
    return info

def get_current_resource(id:str,resources:list):    
    for i, res in enumerate(resources):
        for k,v in res.items():
            if k=='id' and v==id:
                return res
    return None

        
async def convert_doc_seach_doc(doc,resource_file_ids):
        datas = []
        doc_data = safe_get(doc,'data')
        if isinstance(doc_data,list):
            datas+=doc_data
        else:
            datas.append(doc_data)
        info=f'通过查询得到的文档内容如下：\n'
        index =1
        if datas:
            if isinstance(datas,list):
                for data in datas:
                    status = safe_get(data,'status')
                    status_msg = safe_get(data,'status_msg')
                    file_info = safe_get(data,'file_info')
                    
                    resource_id = safe_get(file_info,'resource_id')
                    resource_file_id = safe_get(file_info,'resource_file_id')
                    file_name = safe_get(file_info,'file_name',default='')
                    file_type = safe_get(file_info,'file_type',default='')
                    file_content = safe_get(file_info,'file_content',default='')
                    face_content = safe_get(file_info,'face_content',default='')
                    every_thing_content = safe_get(file_info,'every_thing_content',default='')

                    if status==1:
                        info +=f'{index}. 数字资产id：{resource_id}，文件资源id：{resource_file_id}，isCanDownload:True，名称为：{file_name}，类型为：{file_type}，内容为：{file_content}\n\n'
                        
                    else:
                        
                        info +=f'{index}. 文件资源id：{resource_file_ids[index]}，因该资源尚未申请利用，无法查看详情内容，要获取详情内容，需要申请文档权限。\n\n'
                                                
                    index+=1       
        return info


def convert_tag_seach_doc(doc):
    datalist = safe_get(doc,'data')
    infos=''
    if datalist:
        if isinstance(datalist,list):
            for data in datalist:
                resource_file_id = safe_get(data,'resource_file_id')
                file_name = safe_get(data,'file_name')
                tags = safe_get(data,'tags')
                tags_txt =','.join(tags)
                info =f'资源id：{resource_file_id}，文档名称为：{file_name}，标签为：{tags_txt}\n'
                infos+=info
    return infos


def resource_library_count_doc(resource_library_count):
    # 资产、专题库总数
    library_count = safe_get(resource_library_count,'library_count')
    resource_count = safe_get(resource_library_count,'resource_count')
    resource_size = safe_get(resource_library_count,'resource_size')
    res_info=""
    res_info +=f'系统中专题库总数：{library_count}\n'
    res_info +=f'系统中数字资产总数：{resource_count}\n'
    res_info +=f'系统中数字资产总计文件大小为：{resource_size}\n'
    return res_info

def resource_top_doc(resource_top):
    # 资产访问、下载、申请
    apply_top = safe_get(resource_top,'apply_top')
    download_top = safe_get(resource_top,'download_top')
    view_top = safe_get(resource_top,'view_top')
    res_info=""
    res_info +='申请次数最多的资产Top5：\n'
    for i, res in enumerate(apply_top):
        resource_id=safe_get(res,'resource_id')
        resource_name=safe_get(res,'resource_name')
        times=safe_get(res,'times')
        res_info += f'{i+1}、名称：{resource_name}，申请次数：{times}\n'
        
    res_info +='访问次数最多的资产Top5：\n'
    for i, res in enumerate(view_top):
        resource_id=safe_get(res,'resource_id')
        resource_name=safe_get(res,'resource_name')
        times=safe_get(res,'times')
        res_info += f'{i+1}、名称：{resource_name}，访问次数：{times}\n'
        
    res_info +='下载次数最多的资产Top5：\n'
    for i, res in enumerate(download_top):
        resource_id=safe_get(res,'resource_id')
        resource_name=safe_get(res,'resource_name')
        times=safe_get(res,'times')
        res_info += f'{i+1}、名称：{resource_name}，下载次数：{times}\n'
    
    return res_info
            

def convert_resource_statistic_doc(doc,statistic_type):
    data = safe_get(doc,'data')
    
    if statistic_type =='resource_top':
        return resource_top_doc(data)
    if statistic_type =='resource_library_count':
        return resource_library_count_doc(data)
    if statistic_type =='apply_count':
        apply_count = safe_get(data,'apply_count')
        return f'系统中资产利用申请次数:{apply_count}\n'
    if statistic_type =='resource_download_count':
        resource_download_count = safe_get(data,'resource_download_count')
        return f'系统中资产下载次数:{resource_download_count}\n'
    if statistic_type =='everything_count':
        everything_count = safe_get(data,'everything_count')
        return f'系统中图像训练库数量:{everything_count}\n'
    if statistic_type =='face_count':
        face_count = safe_get(data,'face_count')
        return f'系统中人脸训练库数量:{face_count}\n'
    if statistic_type =='ocr_type':
        ocr_type = safe_get(data,'ocr_type')
        return f'系统中OCR识别中的文字类别数:{ocr_type}\n'
    if statistic_type =='resource_growth':
        resource_growth_count = safe_get(data,'resource_growth')
        return f'资产增长数:{resource_growth_count}\n'

    resources = safe_get(data,statistic_type)
    if resources:
        if statistic_type =='resource_count_by_type':
            res_info = f'按资产类型统计资产数:'
            res_key = '类型数字资产'
        if statistic_type =='resource_file_count_by_type':
            res_info = f'按资产类型统计资产文件数:'
            res_key = '文件'
        if statistic_type =='resource_file_count_by_ext':
            res_info = f'按文件格式统计资产文件数:'
            res_key = '类型文件'
        total = 0
        for i, res in enumerate(resources):
            name=str(res['name'])
            value =str(res['value'])
            total += int(res['value'])
            res_info += f'\n{name}{res_key}总数为{value}'
        res_info += f'\n总数为：{total}\n\n'
    return res_info
    # infos=''
    # if data:
    #     resource_total = safe_get(data,'resource_total')
    #     apply_num = safe_get(resource_total,'apply_num')
    #     library_num = safe_get(resource_total,'library_num')
    #     resource_apply_num = safe_get(resource_total,'resource_apply_num')
    #     resource_num = safe_get(resource_total,'resource_num')
    #     resource_size = safe_get(resource_total,'resource_size')
        
    #     infos += f'\n数字资产总数：{resource_num}个，数字资产利用次数：{resource_apply_num}次，专题库总数：{library_num}个，数字资产利用申请总数：{apply_num},数字资产总计文件大小为：{resource_size}\n'
    #     resource_num = safe_get(data,'resource_num')
    #     resource_size = safe_get(data,'resource_size')
        
    #     infos+= f"\n数字资产数量分布如下：\n"
    #     if isinstance(resource_num,list):
    #         for kv in resource_num:
    #             infos+= f"{kv['name']}类型的数字资产数量为:{kv['value']}个,"
                
    #     infos+= f"\n数字资产存储大小分布如下：\n"
    #     if isinstance(resource_size,list):
    #         for kv in resource_size:
    #             infos+= f"{kv['name']}类型的数字资产存储大小为:{kv['value']},"
            
    #     resource_file_num = safe_get(data,'resource_file_num')
    #     infos+= f"\n文件数量分布如下：\n"
    #     total=0
    #     if isinstance(resource_file_num,list):
    #         for kv in resource_file_num:
    #             total += int(kv['value'])
    #             infos+= f"{kv['name']}类型的文件数量为:{kv['value']}个,"
    #     infos+= f"共计文件数量为:{total}个,"
    # return infos
#endregion

#region  资产列表页面转文档

def convert_asset_list_doc(assets:list):
    info ='当前页面包含的文件列表如下：'
    for i, res in enumerate(assets):
        res_info = f"{i+1}. "
        for k,v in res.items():
            res_info = res_info + k +":"+ str(v) +'，'
        res_info = res_info[:-1] + '。 \n'
        info=info+res_info
    return info

def convert_docs_to_prompt_context(docs: List[Document]) -> str:
    context = []
    for i, doc in enumerate(docs):
        text = (
            doc.page_content.replace("\n", ",")
            .replace("\\n", ",")
            .replace("\r", "")
        )
        text = f"{i + 1}. {text}"
        context.append(text)
    context = "\n".join(context)
    return context


def convert_page_list_doc(assets:list,title=None):
    info=  ''
    if title:
        info = title
    for i, res in enumerate(assets):
        res_info = f"{i+1}. "
        for k,v in res.items():
            if k=='id' or k=='ID':
                continue
            res_info = res_info + k +":"+ str(v) +'，'
        res_info = res_info[:-1] + '。 \n'
        info=info+res_info
    info+=f'共有{len(assets)}个数据'
    return info

#endregion
